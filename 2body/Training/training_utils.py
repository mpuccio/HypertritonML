# this class has been created to generalize the training and to open the file.root just one time
# to achive that alse analysis_utils.py and Significance_Test.py has been modified

import uproot
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.ensemble import AdaBoostClassifier, GradientBoostingClassifier
from sklearn.model_selection import RandomizedSearchCV, GridSearchCV
from sklearn.metrics import roc_auc_score
from sklearn.model_selection import StratifiedKFold
from sklearn.model_selection import train_test_split
import pickle
from scipy.stats import norm
from scipy import stats
import pickle
import matplotlib.pyplot as plt
#------------------------------
import analysis_utils as au
import Significance_Test as ST
import os
from ROOT import TH3D,TFile,gROOT
class Generalized_Analysis:

  def __init__(self,MCfile_name,Datafile_name,cut_presel,bkg_selection):

    #centrality=uproot.open('../../../HypertritonData/EventCounter.root')['fCentrality']
    centrality=uproot.open(Datafile_name)['EventCounter']
    self.Centrality = [[0,10],[10,30],[30,50],[50,90]]
    self.n_ev = [0,0,0,0]
    
    for index in range(1,len(centrality)):
      if index<=self.Centrality[0][1]:
        self.n_ev[0]=centrality[index]+self.n_ev[0]
      elif index<=self.Centrality[1][1]:
        self.n_ev[1]=centrality[index]+self.n_ev[1]
      elif index<=self.Centrality[2][1]:
        self.n_ev[2]=centrality[index]+self.n_ev[2]
      elif index<=self.Centrality[3][1]:
        self.n_ev[3]=centrality[index]+self.n_ev[3]

    self.dfMCSig = uproot.open(MCfile_name)['SignalTable'].pandas.df()
    self.dfMCGen = uproot.open(MCfile_name)['GenTable'].pandas.df()
    self.dfData = uproot.open(Datafile_name)['DataTable'].pandas.df()

    self.dfMCSig['y'] = 1
    self.dfData['y'] = 0
    # dataframe for the background
    self.dfDataF = self.dfData.query(bkg_selection)
    # dataframe for the signal where are applied the preselection cuts
    self.dfMCSigF = self.dfMCSig.query(cut_presel)
    
  def number_events_MC(self,ct_cut=[0,100],pt_cut=[0,12],centrality_cut=[0,100]):
    file = TFile(os.environ['HYPERML_TABLES']+'/EventCounter2.root')
    self.histo_events = gROOT.FindObject('EventCounter')
    n_ev = 0
    for index_ct in range(ct_cut[0]+1,ct_cut[1]+1):
      for index_pt in range(pt_cut[0]*10+1,pt_cut[1]*10+1):
        for index_cen in range(centrality_cut[0]+1,centrality_cut[1]+1):
          n_ev=self.histo_events.GetBinContent(index_ct,index_pt,index_cen)+n_ev
    return n_ev

  
  # function to compute the preselection cuts efficiency
  def EfficiencyPresel(self,ct_cut=[0,100],pt_cut=[0,12],centrality_cut=[0,100]):
    ct_min = ct_cut[0]
    ct_max = ct_cut[1]
    pt_max = pt_cut[1]
    pt_min = pt_cut[0]
    centrality_max = centrality_cut[1]
    centrality_min = centrality_cut[0]
    total_cut = '@ct_min<Ct<@ct_max and @pt_min<HypCandPt<@pt_max and @centrality_min<Centrality<@centrality_max'
    total_cut_gen = '@ct_min<Ct<@ct_max and @pt_min<Pt<@pt_max and @centrality_min<Centrality<@centrality_max'
    
    return len(self.dfMCSigF.query(total_cut))/len(self.dfMCGen.query(total_cut_gen))
  
  def optimize_params(self,dtrain,par):
    scoring = 'auc'
    early_stopping_rounds = 20
    num_rounds = 200
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=23)
    gs_dict = {'first_par': {'name': 'max_depth', 'par_values': [i for i in range(2, 10, 2)]},
          'second_par': {'name': 'min_child_weight', 'par_values':[i for i in range(0, 12, 2)]},
          }
    par['max_depth'],par['min_child_weight'],_ = au.gs_2par(gs_dict, par, dtrain, num_rounds, 42, cv, scoring, early_stopping_rounds)
      
    gs_dict = {'first_par': {'name': 'subsample', 'par_values': [i/10. for i in range(4, 10)]},
          'second_par': {'name': 'colsample_bytree', 'par_values': [i/10. for i in range(8, 10)]},
          }
    par['subsample'],par['colsample_bytree'],_ = au.gs_2par(gs_dict, par, dtrain, num_rounds, 42, cv, scoring, early_stopping_rounds)
    gs_dict = {'first_par': {'name': 'gamma', 'par_values': [i/10. for i in range(0, 11)]}} 
    par['gamma'],_ = au.gs_1par(gs_dict, par, dtrain, num_rounds, 42, cv, scoring, early_stopping_rounds)
    gs_dict = {'first_par': {'name': 'eta', 'par_values': [0.1, 0.05, 0.01, 0.005, 0.001]}}
    par['eta'],n = au.gs_1par(gs_dict, par, dtrain, num_rounds, 42, cv, scoring, early_stopping_rounds)
    return n

  def TrainingAndTest(self,training_columns,params_def,ct_cut=[0,100],pt_cut=[2,3],centrality_cut=[0,10],num_rounds=200,draw=True,ROC=True,optimize=False):
    ct_min = ct_cut[0]
    ct_max = ct_cut[1]
    pt_min = pt_cut[0]
    pt_max = pt_cut[1]
    centrality_min = centrality_cut[0]
    centrality_max = centrality_cut[1]
    
    total_cut = '@ct_min<Ct<@ct_max and @pt_min<HypCandPt<@pt_max and @centrality_min<Centrality<@centrality_max'
    bkg = self.dfDataF.query(total_cut)
    sig = self.dfMCSigF.query(total_cut)
    print('condidates of bkg: ',len(bkg))
    print('condidates of sig: ',len(sig))
    if len(sig) is 0:
      print('no signal -> the model is not trained')
      return 0
    df= pd.concat([sig,bkg])
    traindata,testdata,ytrain,ytest = train_test_split(df[training_columns], df['y'], test_size=0.5)
    dtrain = xgb.DMatrix(data=np.asarray(traindata), label=ytrain, feature_names=training_columns)
    
    if optimize is True:
      num_rounds = self.optimize_params(dtrain,params_def)
      print(total_cut)
      print('num rounds: ',num_rounds)
      print('parameters: ',params_def)

    model = xgb.train(params_def, dtrain,num_boost_round=num_rounds)
    au.plot_output_train_test(model, traindata[training_columns], ytrain, testdata[training_columns], ytest, branch_names=training_columns,raw=True,log=True,draw=draw,ct_cut=ct_cut,pt_cut=pt_cut,centrality_cut=centrality_cut)
    droc = xgb.DMatrix(data=testdata)
    y_pred=model.predict(droc)
    if ROC is True:
      au.plot_roc(ytest,y_pred)
    self.traindata = traindata
    self.testdata =testdata
    self.ytrain = ytrain
    self.ytest = ytest
    return model

  def SetTrainingSets(self,training_columns,ct_cut=[0,100],pt_cut=[2,3],centrality_cut=[0,10]):
    ct_min = ct_cut[0]
    ct_max = ct_cut[1]
    pt_min = pt_cut[0]
    pt_max = pt_cut[1]
    centrality_min = centrality_cut[0]
    centrality_max = centrality_cut[1]
    
    total_cut = '@ct_min<Ct<@ct_max and @pt_min<HypCandPt<@pt_max and @centrality_min<Centrality<@centrality_max'
    bkg = self.dfDataF.query(total_cut)
    sig = self.dfMCSigF.query(total_cut)

    if len(sig) is 0:
      print('no signal ')
      return 
    df= pd.concat([sig,bkg])
    traindata,testdata,ytrain,ytest = train_test_split(df[training_columns], df['y'], test_size=0.5)
    
    self.traindata = traindata
    self.testdata =testdata
    self.ytrain = ytrain
    self.ytest = ytest
    
  def Significance(self,model,training_columns,ct_cut=[0,100],pt_cut=[2,3],centrality_cut=[0,10],draw=False,custom=False,score_shift=0):

    ct_min = ct_cut[0]
    ct_max = ct_cut[1]
    pt_max = pt_cut[1]
    pt_min = pt_cut[0]
    centrality_max = centrality_cut[1]
    centrality_min = centrality_cut[0]
    total_cut = '@ct_min<Ct<@ct_max and @pt_min<HypCandPt<@pt_max and @centrality_min<Centrality<@centrality_max'
    dtest = xgb.DMatrix(data=(self.testdata[training_columns]))
    self.testdata.eval('y = @self.ytest',inplace=True)   
    y_pred = model.predict(dtest,output_margin=True)
    self.testdata.eval('Score = @y_pred',inplace=True)
    efficiency_array=au.EfficiencyVsCuts(self.testdata,ct_cut,pt_cut,centrality_cut)
    
    dfDataSig = self.dfData.query(total_cut)
    dtest = xgb.DMatrix(data=(dfDataSig[training_columns]))
    y_pred = model.predict(dtest,output_margin=True)
    dfDataSig.eval('Score = @y_pred',inplace=True)
    if centrality_cut==[0,90]:
      n_ev=[self.n_ev[0],self.n_ev[1],self.n_ev[2],self.n_ev[3]]
    else:
      i_cen = 0
      for index in range(0,len(self.Centrality)):
        if centrality_cut is self.Centrality[index]:
          i_cen=index
          break
      n_ev=self.n_ev[i_cen]
    print(n_ev)
    cut = ST.SignificanceScan(dfDataSig,ct_cut,pt_cut,centrality_cut,efficiency_array,self.EfficiencyPresel(ct_cut,pt_cut,centrality_cut),n_ev,custom=custom,draw=draw)
    score_list = np.linspace(-3,12.5,156)
    #the efficiency is computed at the score given by SignificanceScan plus something to simplify
    #the bkg fitting

    for index in range(0,len(score_list)):
      if round(score_list[index],2)==round(cut+score_shift,2):
        effBDT=efficiency_array[index]
    return (cut+score_shift,effBDT)

  def correlation_plot(self,training_columns,filename='corr_plot',draw=False):
    training_columns.append('InvMass')
    correlation = self.dfDataF[training_columns].corr(method='pearson')
    plt.imshow(correlation,aspect='auto',  vmin=-1,vmax=1)
    plt.colorbar()
    print(correlation)
    x_pos = np.arange(len(training_columns))
    plt.yticks(x_pos,training_columns)
    plt.xticks(x_pos,training_columns,rotation=90)
    if draw is True:
      plt.show()
    plt.savefig(os.environ['HYPERML_FIGURES']+'/'+filename+'.pdf')
    plt.close()
