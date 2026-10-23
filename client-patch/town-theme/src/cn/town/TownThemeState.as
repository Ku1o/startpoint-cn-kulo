package cn.town {
/** A login snapshot only. The existing asset group and local BGM preference own loading/playback. */
public final class TownThemeState {
 private static var nativeId:int=0;
 private static function record(v:Object):Boolean { return v!=null && typeof(v)==="object" && !(v is Array); }
 private static function integer(v:Object,max:Number):Boolean {
  return v is Number && isFinite(Number(v)) && Number(v)>=0 && Number(v)<=max && Math.floor(Number(v))==Number(v);
 }
 public static function captureResponse(raw:Object):void {
  if(!record(raw) || !record(raw.data_headers) || raw.data_headers.result_code!==1 || !record(raw.data))return;
  var d:Object=raw.data;
  // Legacy full-load shape verified against the server's client-player serializer.
  // Ordinary partial user/option/party responses cannot meet this conjunction.
  var legacyLoad:Boolean=!d.hasOwnProperty("town_presentation_load") && record(d.user_info) && record(d.user_option)
    && record(d.user_character_list) && record(d.user_party_group_list);
  if(d.town_presentation_load!==true && !legacyLoad)return;
  // Reset on every successful load before validating its optional snapshot.
  nativeId=0;
  // Legacy servers cannot establish a manual policy even if an unrelated field shares the name.
  if(legacyLoad)return;
  var p:Object=d.town_presentation;
  if(!record(p) || p.schema_version!==1 || !integer(p.revision,9007199254740991)
    || !(p.catalog_digest is String) || !/^[0-9a-f]{64}$/.test(p.catalog_digest))return;
  if(p.mode==="auto")return;
  if(p.mode!=="manual" || !(p.theme_id is String) || !/^[a-z][a-z0-9_\-]{0,127}$/.test(p.theme_id)
    || !integer(p.town_content_id,2147483647) || Number(p.town_content_id)<1)return;
  // Copy the scalar, never retain the mutable response or master object.
  nativeId=int(p.town_content_id);
 }
 private static function path(v:Object):Boolean {
  return v is String && v.length>0 && v.length<1024 && v.indexOf("..")<0 && v.indexOf(":")<0 && v.indexOf("\\")<0;
 }
 private static function option(v:Object):Boolean {
  return v!=null && (v.index===1 || (v.index===0 && v.params is Array && v.params.length===1));
 }
 private static function supported(row:Object):Boolean {
  if(row==null || !path(row.string_id) || !path(row.background_image) || !path(row.background_blured_image)
    || !path(row.bgm) || !option(row.mask_image) || !option(row.particle))return false;
  if(row.mask_image.index===0 && !path(row.mask_image.params[0]))return false;
  if(row.particle.index===0) {
   var p:Object=row.particle.params[0];
   if(p==null || !path(p.animation) || !integer(p.emittion_rate,2147483647)
     || !integer(p.framerate_division,2147483647) || p.framerate_division<1
     || !integer(p.width,2147483647) || !integer(p.height,2147483647)
     || !(p.vx is Number) || !isFinite(p.vx) || !(p.vy is Number) || !isFinite(p.vy)
     || !(p.min_scale is Number) || !isFinite(p.min_scale) || p.min_scale<=0
     || !(p.max_scale is Number) || !isFinite(p.max_scale) || p.max_scale<p.min_scale
     || p.blend_mode==null || (p.blend_mode.index!==0 && p.blend_mode.index!==1))return false;
  }
  return true;
 }
 /** Null means execute the complete original time algorithm. No five-theme list exists here. */
 public static function select(repository:Object):Object {
  if(nativeId==0 || repository==null)return null;
  try {
   var table:Object=repository.townContentTable;
   if(table==null || !table.exists(nativeId) || !supported(table.get(nativeId)))return null;
   var content:Object=repository.getTownContentById(nativeId);
   return content!=null && content.id===nativeId && supported(content.values) ? content : null;
  } catch(e:Error) { return null; }
 }
} }
