package pinball.common.data.exBoost {
import fixture.CommonHarness;
import haxe.IMap;
import haxe.ds.IntMap;
public dynamic class ExBoostRepository {public var list:IntMap=new IntMap();public function getAllIds():IMap{return list;}public function getById(i:int):Object{return list.h[i];}public function getIncreasedExBoostItems(v:Object,before:IMap):Array{CommonHarness.events.push({kind:"recording-ex-item-diff-dependency",data:v});return [];}}}