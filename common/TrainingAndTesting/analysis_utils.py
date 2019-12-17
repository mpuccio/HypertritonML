import io
import math
import os
from contextlib import redirect_stdout

import numpy as np
from sklearn.model_selection import cross_val_score
import yaml
import xgboost as xgb
from ROOT import ROOT as RR
from ROOT import (TF1, TH1D, TH2D, TH3D, TCanvas, TFile, TPaveStats, TPaveText,
                  gDirectory, gStyle)


# target function for the bayesian hyperparameter optimization
def evaluate_hyperparams(data, training_columns, reg_params, max_depth, learning_rate, n_estimators, gamma,
                         min_child_weight, subsample, colsample_bytree, nfold=5):
    params = {'max_depth': int(max_depth),
              'learning_rate': learning_rate,
              'n_estimators': int(n_estimators),
              'gamma': gamma,
              'min_child_weight': int(min_child_weight),
              'subsample': subsample,
              'colsample_bytree': colsample_bytree}
    params = {**reg_params, **params}

    model = xgb.XGBClassifier(**params)
    return np.mean(cross_val_score(model, data[0][training_columns], data[1], cv=nfold, scoring='roc_auc')) * 100. - 99.


def gs_1par(gs_dict, par_dict, train_data, num_rounds, seed, folds, metrics, n_early_stop):
    fp_dict = gs_dict['first_par']
    gs_params = fp_dict['par_values']

    max_auc = 0.
    best_params = None
    for val in gs_params:
        # Update our parameters
        par_dict[fp_dict['name']] = val

        # Run CV
        trap = io.StringIO()
        with redirect_stdout(trap):
            cv_results = xgb.cv(par_dict, train_data, num_boost_round=num_rounds, seed=seed,
                                folds=folds, metrics=metrics, early_stopping_rounds=n_early_stop)

        # Update best AUC
        mean_auc = cv_results['test-auc-mean'].max()
        boost_rounds = cv_results['test-auc-mean'].idxmax()
        mean_std = cv_results['test-auc-std'][boost_rounds]

        if mean_auc > max_auc:
            max_auc = mean_auc
            max_std = mean_std
            best_params = (val, boost_rounds)

    return (best_params)


def gs_2par(gs_dict, par_dict, train_data, num_rounds, seed, folds, metrics, n_early_stop):
    fp_dict = gs_dict['first_par']
    sp_dict = gs_dict['second_par']

    gs_params = [(first_val, second_val) for first_val in fp_dict['par_values'] for second_val in sp_dict['par_values']]

    max_auc = 0.
    best_params = None
    for first_val, second_val in gs_params:
        # Update our parameters
        par_dict[fp_dict['name']] = first_val
        par_dict[sp_dict['name']] = second_val

        # Run CV
        trap = io.StringIO()
        with redirect_stdout(trap):
            cv_results = xgb.cv(par_dict, train_data, num_boost_round=num_rounds, seed=seed,
                                folds=folds, metrics=metrics, early_stopping_rounds=n_early_stop)

        # Update best AUC
        mean_auc = cv_results['test-auc-mean'].max()
        boost_rounds = cv_results['test-auc-mean'].idxmax()
        mean_std = cv_results['test-auc-std'][boost_rounds]

        if mean_auc > max_auc:
            max_auc = mean_auc
            max_std = mean_std
            best_params = (first_val, second_val, boost_rounds)

    return (best_params)


# nevents assumed to be the number of events in 1% bins
def expected_signal_counts(bw, pt_range, eff, cent_range, nevents):
    hyp2he3 = 0.4 * 0.25  # Very optimistic, considering it constant with centrality
    cent_bins = [10, 40, 90]

    signal = 0
    for cent in range(cent_range[0]+1, cent_range[1]):
        for index in range(0, 3):
            if cent < cent_bins[index]:
                signal = signal + nevents[cent] * bw[index].Integral(pt_range[0], pt_range[1], 1e-8)
                break

    return int(round(2*signal * eff * hyp2he3))


def significance_error(signal, background):
    signal_error = np.sqrt(signal + 1e-10)
    background_error = np.sqrt(background + 1e-10)

    sb = signal + background + 1e-10
    sb_sqrt = np.sqrt(sb)

    s_propag = (sb_sqrt + signal / (2 * sb_sqrt))/sb * signal_error
    b_propag = signal / (2 * sb_sqrt)/sb * background_error

    if signal+background == 0:
        return 0
    return np.sqrt(s_propag * s_propag + b_propag * b_propag)


def expo(x, tau):
    return np.exp(-x / (tau * 0.029979245800))


def h2_bdteff(ptbin, ctbin, name='BDTeff'):
    th2 = TH2D(name, ';#it{p}_{T} (GeV/#it{c});c#it{t} (cm);BDT efficiency', len(ptbin)-1,
               np.array(ptbin, 'double'), len(ctbin) - 1, np.array(ctbin, 'double'))

    return th2


def h2_seleff(ptbin, ctbin, name='SelEff'):
    th2 = TH2D(name, ';#it{p}_{T} (GeV/#it{c});c#it{t} (cm);Preselection efficiency',
               len(ptbin)-1, np.array(ptbin, 'double'), len(ctbin)-1, np.array(ctbin, 'double'))

    return th2


def h2_rawcounts(ptbin, ctbin, name='RawCounts'):
    th2 = TH2D(name, ';#it{p}_{T} (GeV/#it{c});c#it{t} (cm);Raw counts', len(ptbin)-1,
               np.array(ptbin, 'double'), len(ctbin) - 1, np.array(ctbin, 'double'))

    return th2


def h2_mcsigma(ptbin, ctbin, name='SigmaPtCt'):
    th2 = TH2D(name, ';#it{p}_{T} (GeV/#it{c});c#it{t} (cm);#sigma', len(ptbin)-1,
               np.array(ptbin, 'double'), len(ctbin) - 1, np.array(ctbin, 'double'))

    return th2


def h3_minvptct(ptbin, ctbin, name='InvMassPtCt'):
    th3 = TH3D(name, ';#it{M} (^{3}He + #pi^{-}) (GeV/#it{c}^{2});#it{p}_{T} (GeV/#it{c});c#it{t} (cm)', 40, np.array(np.arange(
        2.96, 3.05225, 0.00225), 'double'), len(ptbin) - 1, np.array(ptbin, 'double'), len(ctbin) - 1, np.array(ctbin, 'double'))

    return th3


def fit(
        counts, ct_range, pt_range, cent_class, tdirectory=None, nsigma=3, signif=0, errsignif=0, name='', bins=45,
        model="expo", fixsigma=-1, sigmaLimits=None):
    histo = TH1D(
        "ct{}{}_pT{}{}_cen{}{}_{}_{}".format(
            ct_range[0],
            ct_range[1],
            pt_range[0],
            pt_range[1],
            cent_class[0],
            cent_class[1],
            name,
            model),
        "", bins, 2.96, 3.05)
    for index in range(0, len(counts)):
        histo.SetBinContent(index+1, counts[index])
        histo.SetBinError(index+1, math.sqrt(counts[index]))
    return fitHist(histo, ct_range, pt_range, cent_class, tdirectory, nsigma, signif, errsignif, model, fixsigma, sigmaLimits)


def fitHist(
        histo, ct_range, pt_range, cent_class, tdirectory=None, nsigma=3, signif=0, errsignif=0, model="expo",
        fixsigma=-1, sigmaLimits=None):
    if tdirectory:
        tdirectory.cd()

    cv = TCanvas("cv_{}".format(histo.GetName()))

    if 'pol' in str(model):
        nBkgPars = int(model[3]) + 1
    elif 'expo' in str(model):
        nBkgPars = 2
    else:
        print("Unsupported model {}".format(model))

    fitTpl = TF1("fitTpl", "{}(0)+gausn({})".format(model, nBkgPars), 0, 5)
    for i in range(0, nBkgPars):
        fitTpl.SetParName(i, 'B_{}'.format(i))

    fitTpl.SetParName(nBkgPars, "N_{sig}")
    fitTpl.SetParName(nBkgPars + 1, "#mu")
    fitTpl.SetParName(nBkgPars + 2, "#sigma")
    bkgTpl = TF1("fitTpl", "{}(0)".format(model), 0, 5)
    sigTpl = TF1("fitTpl", "gausn(0)", 0, 5)
    fitTpl.SetNpx(300)
    fitTpl.SetLineWidth(2)
    fitTpl.SetLineColor(2)
    bkgTpl.SetNpx(300)
    bkgTpl.SetLineWidth(2)
    bkgTpl.SetLineStyle(2)
    bkgTpl.SetLineColor(2)

    fitTpl.SetParameter(nBkgPars, 40)
    fitTpl.SetParLimits(nBkgPars, 0.001, 10000)
    fitTpl.SetParameter(nBkgPars + 1, 2.991)
    fitTpl.SetParLimits(nBkgPars + 1, 2.986, 3)
    if sigmaLimits != None:
        fitTpl.SetParameter(nBkgPars + 2, 0.5 * (sigmaLimits[0] + sigmaLimits[1]))
        fitTpl.SetParLimits(nBkgPars + 2, sigmaLimits[0], sigmaLimits[1])
    elif fixsigma > 0:
        fitTpl.FixParameter(nBkgPars + 2, fixsigma)
    else:
        fitTpl.SetParameter(nBkgPars + 2, 0.002)
        fitTpl.SetParLimits(nBkgPars + 2, 0.001, 0.003)
    # gStyle.SetOptFit(0)
    ####################

    histo.UseCurrentStyle()
    histo.SetLineColor(1)
    histo.SetMarkerStyle(20)
    histo.SetMarkerColor(1)
    ax_titles = ';m (^{3}He + #pi) (GeV/#it{c})^{2};Counts' + ' / {} MeV'.format(round(1000 * histo.GetBinWidth(1), 2))
    histo.SetTitle(ax_titles)
    histo.SetMaximum(1.5 * histo.GetMaximum())
    histo.Fit(fitTpl, "QRL", "", 2.96, 3.04)
    histo.Fit(fitTpl, "QRL", "", 2.96, 3.04)
    histo.SetDrawOption("e")
    histo.GetXaxis().SetRangeUser(2.96, 3.04)
    bkgTpl.SetParameters(fitTpl.GetParameters())
    bkgTpl.SetLineColor(600)
    bkgTpl.SetLineStyle(2)
    bkgTpl.Draw("same")
    sigTpl.SetParameter(0, fitTpl.GetParameter(nBkgPars))
    sigTpl.SetParameter(1, fitTpl.GetParameter(nBkgPars+1))
    sigTpl.SetParameter(2, fitTpl.GetParameter(nBkgPars+2))
    sigTpl.SetLineColor(600)
    # sigTpl.Draw("same")
    mu = fitTpl.GetParameter(nBkgPars+1)
    sigma = fitTpl.GetParameter(nBkgPars+2)
    sigmaErr = fitTpl.GetParError(nBkgPars+2)
    signal = fitTpl.GetParameter(nBkgPars) / histo.GetBinWidth(1)
    errsignal = fitTpl.GetParError(nBkgPars) / histo.GetBinWidth(1)
    bkg = bkgTpl.Integral(mu - nsigma * sigma, mu + nsigma * sigma) / histo.GetBinWidth(1)

    if bkg > 0:
        errbkg = math.sqrt(bkg)
    else:
        errbkg = 0

    if signal+bkg > 0:
        signif = signal/math.sqrt(signal+bkg)
        deriv_sig = 1/math.sqrt(signal+bkg)-signif/(2*(signal+bkg))
        deriv_bkg = -signal/(2*(math.pow(signal+bkg, 1.5)))
        errsignif = math.sqrt((errsignal*deriv_sig)**2+(errbkg*deriv_bkg)**2)
    else:
        print('sig+bkg<0')
        signif = 0
        errsignif = 0

    pinfo2 = TPaveText(0.5, 0.5, 0.91, 0.9, "NDC")
    pinfo2.SetBorderSize(0)
    pinfo2.SetFillStyle(0)
    pinfo2.SetTextAlign(30+3)
    pinfo2.SetTextFont(42)
    string = 'ALICE Internal, Pb-Pb 2018 {}-{}%'.format(cent_class[0], cent_class[1])
    pinfo2.AddText(string)
    string = '{}^{3}_{#Lambda}H#rightarrow ^{3}He#pi + c.c., %i #leq #it{ct} < %i cm %i #leq #it{p}_{T} < %i GeV/#it{c} ' % (
        ct_range[0], ct_range[1], pt_range[0], pt_range[1])
    pinfo2.AddText(string)
    string = 'Significance ({:.0f}#sigma) {:.1f} #pm {:.1f} '.format(nsigma, signif, errsignif)
    pinfo2.AddText(string)

    string = 'S ({:.0f}#sigma) {:.0f} #pm {:.0f} '.format(nsigma, signal, errsignal)
    pinfo2.AddText(string)
    string = 'B ({:.0f}#sigma) {:.0f} #pm {:.0f}'.format(nsigma, bkg, errbkg)
    pinfo2.AddText(string)
    if bkg > 0:
        ratio = signal/bkg
        string = 'S/B ({:.0f}#sigma) {:.4f} '.format(nsigma, ratio)
    pinfo2.AddText(string)
    pinfo2.Draw()
    gStyle.SetOptStat(0)
    st = histo.FindObject('stats')
    if isinstance(st, TPaveStats):
        st.SetX1NDC(0.12)
        st.SetY1NDC(0.62)
        st.SetX2NDC(0.40)
        st.SetY2NDC(0.90)
    if tdirectory:
        tdirectory.cd()
        histo.Write()
        cv.Write()
    return (signal, errsignal, signif, errsignif, sigma, sigmaErr)


def fitUnbinned(
        data, ct_range, pt_range, cent_class, tdirectory=None, nsigma=3, signif=0, errsignif=0, model="expo",
        fixsigma=-1, sigmaLimits=None):
    if tdirectory:
        tdirectory.cd()

    # cv = TCanvas("cv_{}".format(histo.GetName()))

    dataRange = RR.Fit.DataRange(2.96, 3.05)
    unBinDataSet = RR.Fit.UnBinData(len(data), data, dataRange)

    if 'pol' in str(model):
        nBkgPars = int(model[3]) + 1
    elif 'expo' in str(model):
        nBkgPars = 2
    else:
        print("Unsupported model {}".format(model))

    fitTpl = TF1("fitTpl", "{}(0)+gausn({})".format(model, nBkgPars), 0, 5)
    for i in range(0, nBkgPars):
        fitTpl.SetParName(i, 'B_{}'.format(i))

    fitTpl.SetParName(nBkgPars, "N_{sig}")
    fitTpl.SetParName(nBkgPars + 1, "#mu")
    fitTpl.SetParName(nBkgPars + 2, "#sigma")
    bkgTpl = TF1("fitTpl", "{}(0)".format(model), 0, 5)
    sigTpl = TF1("fitTpl", "gausn(0)", 0, 5)
    fitTpl.SetNpx(300)
    fitTpl.SetLineWidth(2)
    fitTpl.SetLineColor(2)
    bkgTpl.SetNpx(300)
    bkgTpl.SetLineWidth(2)
    bkgTpl.SetLineStyle(2)
    bkgTpl.SetLineColor(2)

    fitFunction = RR.Math.WrappedMultiTF1(fitTpl, 1)
    fitter = RR.Fit.Fitter()
    fitter.SetFunction(fitFunction, False)

    fitter.Config().ParSettings(nBkgPars).SetValue(10)
    fitter.Config().ParSettings(nBkgPars).SetLimits(0.001, 10000)
    fitter.Config().ParSettings(nBkgPars + 1).SetValue(2.991)
    fitter.Config().ParSettings(nBkgPars + 1).SetLimits(2.986, 3)
    if sigmaLimits != None:
        fitter.Config().ParSettings(nBkgPars + 2).SetValue(0.5 * (sigmaLimits[0] + sigmaLimits[1]))
        fitter.Config().ParSettings(nBkgPars + 2).SetLimits(sigmaLimits[0], sigmaLimits[1])
    elif fixsigma > 0:
        fitter.Config().ParSettings(nBkgPars + 2).SetValue(fixsigma)
        fitter.Config().ParSettings(nBkgPars + 2).Fix()
    else:
        fitter.Config().ParSettings(nBkgPars + 2).SetValue(0.002)
        fitter.Config().ParSettings(nBkgPars + 2).SetLimits(0.001, 0.003)

    # gStyle.SetOptFit(0)
    # ####################

    # histo.UseCurrentStyle()
    # histo.SetLineColor(1)
    # histo.SetMarkerStyle(20)
    # histo.SetMarkerColor(1)
    # ax_titles = ';m (^{3}He + #pi) (GeV/#it{c})^{2};Counts' + ' / {} MeV'.format(round(1000 * histo.GetBinWidth(1), 2))
    # histo.SetTitle(ax_titles)
    # histo.SetMaximum(1.5 * histo.GetMaximum())
    fitter.LikelihoodFit(unBinDataSet, True)
    # print(fitter.Result().FittedFunction().Parameters()[nBkgPars+1])
    # histo.Fit(fitTpl, "QRL", "", 2.96, 3.04)
    # histo.SetDrawOption("e")
    # histo.GetXaxis().SetRangeUser(2.96, 3.04)
    # bkgTpl.SetParameters(fitTpl.GetParameters())
    # bkgTpl.SetLineColor(600)
    # bkgTpl.SetLineStyle(2)
    # bkgTpl.Draw("same")
    # sigTpl.SetParameter(0, fitTpl.GetParameter(nBkgPars))
    # sigTpl.SetParameter(1, fitTpl.GetParameter(nBkgPars+1))
    # sigTpl.SetParameter(2, fitTpl.GetParameter(nBkgPars+2))
    # sigTpl.SetLineColor(600)
    # sigTpl.Draw("same")
    # mu = fitTpl.GetParameter(nBkgPars+1)
    # sigma = fitTpl.GetParameter(nBkgPars+2)
    # sigmaErr = fitTpl.GetParError(nBkgPars+2)
    # signal = fitTpl.GetParameter(nBkgPars)
    # errsignal = fitTpl.GetParError(nBkgPars)
    # bkg = bkgTpl.Integral(mu - nsigma * sigma, mu + nsigma * sigma)

    # if bkg > 0:
    #     errbkg = math.sqrt(bkg)
    # else:
    #     errbkg = 0

    # if signal+bkg > 0:
    #     signif = signal/math.sqrt(signal+bkg)
    #     deriv_sig = 1/math.sqrt(signal+bkg)-signif/(2*(signal+bkg))
    #     deriv_bkg = -signal/(2*(math.pow(signal+bkg, 1.5)))
    #     errsignif = math.sqrt((errsignal*deriv_sig)**2+(errbkg*deriv_bkg)**2)
    # else:
    #     print('sig+bkg<0')
    #     signif = 0
    #     errsignif = 0

    # pinfo2 = TPaveText(0.5, 0.5, 0.91, 0.9, "NDC")
    # pinfo2.SetBorderSize(0)
    # pinfo2.SetFillStyle(0)
    # pinfo2.SetTextAlign(30+3)
    # pinfo2.SetTextFont(42)
    # string = 'ALICE Internal, Pb-Pb 2018 {}-{}%'.format(cent_class[0], cent_class[1])
    # pinfo2.AddText(string)
    # string = '{}^{3}_{#Lambda}H#rightarrow ^{3}He#pi + c.c., %i #leq #it{ct} < %i cm %i #leq #it{p}_{T} < %i GeV/#it{c} ' % (
    #     ct_range[0], ct_range[1], pt_range[0], pt_range[1])
    # pinfo2.AddText(string)
    # string = 'Significance ({:.0f}#sigma) {:.1f} #pm {:.1f} '.format(nsigma, signif, errsignif)
    # pinfo2.AddText(string)

    # string = 'S ({:.0f}#sigma) {:.0f} #pm {:.0f} '.format(nsigma, signal, errsignal)
    # pinfo2.AddText(string)
    # string = 'B ({:.0f}#sigma) {:.0f} #pm {:.0f}'.format(nsigma, bkg, errbkg)
    # pinfo2.AddText(string)
    # if bkg > 0:
    #     ratio = signal/bkg
    #     string = 'S/B ({:.0f}#sigma) {:.4f} '.format(nsigma, ratio)
    # pinfo2.AddText(string)
    # pinfo2.Draw()
    # gStyle.SetOptStat(0)
    # st = histo.FindObject('stats')
    # if isinstance(st, TPaveStats):
    #     st.SetX1NDC(0.12)
    #     st.SetY1NDC(0.62)
    #     st.SetX2NDC(0.40)
    #     st.SetY2NDC(0.90)
    # if tdirectory:
    #     tdirectory.cd()
    #     histo.Write()
    #     cv.Write()
    # return (signal, errsignal, signif, errsignif, sigma, sigmaErr)


def split_name(split_type=''):
    if split_type=='':
        return split_type
    else:
        return '_'+split_type    

def create_ranges(score_bdteff_dict) :
    ranges_best=[]
    ranges_scan=[]
    score_keys = score_bdteff_dict.keys()
    for k in score_keys:
        best=round(score_bdteff_dict[k]['sig_scan'][1],2)
        ranges_best.append(best)
        ranges_scan.append([best-0.1,best+0.1,0.01])

    ranges_dict= {
        'BEST' : ranges_best,
        'SCAN' : ranges_scan
    }
    return ranges_dict

    


   

