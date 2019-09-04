#include <iostream>
#include <vector>

#include <TFile.h>
#include <TH1D.h>
#include <TRandom3.h>
#include <TTree.h>
#include <TTreeReader.h>
#include <TTreeReaderArray.h>
#include <TTreeReaderValue.h>

#include "AliAnalysisTaskHyperTriton2He3piML.h"
#include "AliPID.h"

#include "../../common/GenerateTable/Common.h"
#include "../../common/GenerateTable/GenTable2.h"
#include "../../common/GenerateTable/Table2.h"

void GenerateTableFromMC(bool reject = true) {

  string hypDataDir  = getenv("HYPERML_DATA_2");
  string hypTableDir = getenv("HYPERML_TABLES_2");
  string hypUtilsDir = getenv("HYPERML_UTILS");

  string inFileName = "HyperTritonTree_19d2.root";
  string inFileArg  = hypDataDir + "/" + inFileName;

  string outFileName = "SignalTable.root";
  string outFileArg  = hypTableDir + "/" + outFileName;

  string bwFileName = "BlastWaveFits.root";
  string bwFileArg  = hypUtilsDir + "/" + bwFileName;

  // get the bw functions for the pt rejection
  TFile bwFile(bwFileArg.data());

  TF1 *BlastWave{nullptr};
  TF1 *BlastWave0{(TF1 *)bwFile.Get("BlastWave/BlastWave0")};
  TF1 *BlastWave1{(TF1 *)bwFile.Get("BlastWave/BlastWave1")};
  TF1 *BlastWave2{(TF1 *)bwFile.Get("BlastWave/BlastWave2")};

  float max  = 0.0;
  float max0 = BlastWave0->GetMaximum();
  float max1 = BlastWave1->GetMaximum();
  float max2 = BlastWave2->GetMaximum();

  // read the tree
  TFile *inFile = new TFile(inFileArg.data(), "READ");

  TTreeReader fReader("_custom/fTreeV0", inFile);
  TTreeReaderArray<RHyperTritonHe3pi> RHyperVec = {fReader, "RHyperTriton"};
  TTreeReaderArray<SHyperTritonHe3pi> SHyperVec = {fReader, "SHyperTriton"};
  TTreeReaderValue<RCollision> RColl            = {fReader, "RCollision"};

  // new flat tree with the features
  TFile outFile(outFileArg.data(), "RECREATE");
  Table2 table("SignalTable", "Signal Table");
  GenTable2 genTable("GenTable", "Generated particle table");

  while (fReader.Next()) {
    auto cent = RColl->fCent;

    if (cent <= 10) {
      BlastWave = BlastWave0;
      max       = max0;
    }
    if (cent > 10. && cent <= 40.) {
      BlastWave = BlastWave1;
      max       = max1;
    } else {
      BlastWave = BlastWave2;
      max       = max2;
    }
    for (auto &SHyper : SHyperVec) {

      bool matter = SHyper.fPdgCode > 0;

      double pt = std::hypot(SHyper.fPxHe3 + SHyper.fPxPi, SHyper.fPyHe3 + SHyper.fPyPi);

      float BlastWaveNum = BlastWave->Eval(pt) / max;
      if (reject) {
        if (BlastWaveNum < gRandom->Rndm()) continue;
      }
      genTable.Fill(SHyper, *RColl);
      int ind = SHyper.fRecoIndex;

      if (ind >= 0) {
        auto &RHyper = RHyperVec[ind];
        table.Fill(RHyper, *RColl);
      }
    }
  }

  outFile.cd();
  table.Write();
  genTable.Write();

  outFile.Close();

  std::cout << "\nDerived tables from MC generated!\n" << std::endl;
}
