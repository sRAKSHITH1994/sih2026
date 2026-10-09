#include <iostream>
#include <vector>
#include <chrono>
#include <algorithm>
#include <iomanip>
#include "edge_mlp.h"
#include "model_weights.h"
int main(){
 std::vector<FeatureVector> rows;FeatureVector f{};f.windowReady=true;
 while(std::cin>>f.x[0]){for(int i=1;i<56;++i)std::cin>>f.x[i];rows.push_back(f);}
 if(rows.empty())return 2;
 volatile float checksum=0;std::vector<double> ms;
 for(const auto& row:rows){auto start=std::chrono::steady_clock::now();auto result=runEdgeML(row);
  auto stop=std::chrono::steady_clock::now();checksum+=result.probability;
  ms.push_back(std::chrono::duration<double,std::milli>(stop-start).count());}
 double total=0;for(double t:ms)total+=t;std::sort(ms.begin(),ms.end());
 const size_t weights=sizeof(ML_W1)+sizeof(ML_W2)+sizeof(ML_W3)+sizeof(ML_B1)+sizeof(ML_B2)+sizeof(ML_B3);
 std::cout<<std::setprecision(10)<<"{\"weight_bias_bytes\":"<<weights<<",\"normalization_bytes\":"<<sizeof(INPUT_MEAN)+sizeof(INPUT_STD)
 <<",\"all_float_array_bytes\":"<<weights+sizeof(INPUT_MEAN)+sizeof(INPUT_STD)<<",\"samples\":"<<ms.size()
 <<",\"mean_inference_ms\":"<<total/ms.size()<<",\"p95_inference_ms\":"<<ms[(ms.size()-1)*95/100]<<",\"checksum\":"<<checksum<<"}\n";
}
