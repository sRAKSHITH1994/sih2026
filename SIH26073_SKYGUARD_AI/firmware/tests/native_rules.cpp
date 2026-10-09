#include "detection_rules.h"
extern "C" {
void* rules_create(){return new EdgeRules::Engine();}
void rules_destroy(void* p){delete static_cast<EdgeRules::Engine*>(p);}
void rules_evaluate(void* p,const float* f,int ready,float nominal,int* cls,float* severity){
 auto r=static_cast<EdgeRules::Engine*>(p)->evaluate(f,ready,nominal);*cls=r.cls;*severity=r.severity;
}
}
