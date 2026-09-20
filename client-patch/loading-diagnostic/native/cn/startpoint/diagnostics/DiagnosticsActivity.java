package cn.startpoint.diagnostics;

import android.app.Activity;
import android.app.ActivityManager;
import android.app.ApplicationExitInfo;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Intent;
import android.content.ContentValues;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.MediaStore;
import android.widget.*;
import android.view.View;
import android.graphics.Color;
import org.json.*;
import java.io.*;
import java.text.SimpleDateFormat;
import java.util.*;

/** Native phone export UI; usable from its own launcher icon without loading the AIR scene. */
public final class DiagnosticsActivity extends Activity {
    private TextView status;
    private Button share,copy,save,refresh;
    private File ready;
    private String summary="正在读取记录。";
    private boolean busy=false;
    private String pendingExport;
    private static final int SAVE_DOCUMENT=4102;

    protected void onCreate(Bundle state) {
        super.onCreate(state);
        if(state!=null)pendingExport=state.getString("pendingExport");
        ScrollView scroll=new ScrollView(this);
        LinearLayout body=new LinearLayout(this);body.setOrientation(LinearLayout.VERTICAL);
        int p=dp(22);body.setPadding(p,p,p,p);body.setBackgroundColor(Color.rgb(246,248,250));scroll.addView(body);
        TextView title=text("共斗加载诊断",26);body.addView(title);
        body.addView(text(BuildInfo.BUILD+"\n闪退后重新打开这里，就可以分享上次记录。",15));
        status=text("正在读取本地记录…",16);status.setTextIsSelectable(true);body.addView(status);
        share=button(body,"分享日志文件",new View.OnClickListener(){public void onClick(View v){share();}});
        copy=button(body,"复制诊断摘要",new View.OnClickListener(){public void onClick(View v){copySummary();}});
        save=button(body,Build.VERSION.SDK_INT>=29?"保存到下载文件夹":"保存到文件",new View.OnClickListener(){public void onClick(View v){saveDocument();}});
        refresh=button(body,"刷新记录",new View.OnClickListener(){public void onClick(View v){prepare();}});
        body.addView(text("分享后在手机上选择 QQ、微信等应用，再选择收件人发送。\n日志包含最近加载记录与可取得的系统退出信息。请在卸载或清除游戏数据前导出。",14));
        button(body,"关闭",new View.OnClickListener(){public void onClick(View v){finish();}});
        setContentView(scroll);prepare();
    }
    private int dp(int value){return Math.round(value*getResources().getDisplayMetrics().density);}
    private TextView text(String value,int size){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(Color.rgb(29,45,58));t.setPadding(0,dp(8),0,dp(12));return t;}
    private Button button(LinearLayout body,String label,View.OnClickListener listener){Button b=new Button(this);b.setText(label);b.setTextSize(17);b.setAllCaps(false);b.setOnClickListener(listener);body.addView(b,new LinearLayout.LayoutParams(-1,dp(56)));return b;}
    private void enable(boolean value){share.setEnabled(value);copy.setEnabled(value);save.setEnabled(value);refresh.setEnabled(value);}
    protected void onSaveInstanceState(Bundle state){state.putString("pendingExport",pendingExport);super.onSaveInstanceState(state);}
    protected void onResume(){super.onResume();if(ready!=null && !busy && pendingExport==null)prepare();}

    private void prepare(){
        if(busy)return;busy=true;enable(false);status.setText("正在整理本地记录…");
        new Thread(new Runnable(){public void run(){
            File built=null;String message;
            try{
                File data=new File(getApplicationInfo().dataDir);
                File air=LogStore.findAirDirectory(data,getPackageName());
                Map<String,byte[]> entries=LogStore.snapshot(air);
                JSONObject meta=new JSONObject();
                meta.put("diagnosticBuild",BuildInfo.BUILD);meta.put("airUuid",BuildInfo.AIR_UUID);
                meta.put("baselineApkSha256",BuildInfo.BASE_APK_SHA256);
                meta.put("package",getPackageName());meta.put("appVersion",getPackageManager().getPackageInfo(getPackageName(),0).versionName);
                meta.put("exportEpochMs",System.currentTimeMillis());meta.put("androidSdk",Build.VERSION.SDK_INT);
                meta.put("androidRelease",Build.VERSION.RELEASE);meta.put("manufacturer",Build.MANUFACTURER);meta.put("model",Build.MODEL);
                meta.put("airDirectoryFound",air!=null);meta.put("automaticUpload",false);
                meta.put("memoryNote","AIR/private memory are point samples; system PSS/RSS may be absent or older than process exit, not exact peaks.");
                meta.put("interruptionNote","Missing session.complete is not proof of a crash; cancellation, killing or an incomplete write can also cause it.");
                meta.put("exitHistory",exits(entries));
                message=describe(entries,meta);
                entries.put("metadata.json",meta.toString(2).getBytes("UTF-8"));
                entries.put("summary.txt",message.getBytes("UTF-8"));
                File exports=LogStore.inside(getCacheDir(),"cn-loading-diagnostic-exports");
                String name="StarPoint-Loading-"+new SimpleDateFormat("yyyyMMdd-HHmmss-SSS",Locale.US).format(new Date())+".zip";
                File target=LogStore.exportFile(exports,name);LogStore.writeZip(target,entries);LogStore.trimExports(exports,target);built=target;
            }catch(Exception e){message="整理日志失败（"+e.getClass().getSimpleName()+"）。可关闭后重试；游戏存档不受影响。";}
            final File result=built;final String description=message;
            runOnUiThread(new Runnable(){public void run(){if(isFinishing() || isDestroyed())return;ready=result;summary=description;status.setText(description);busy=false;enable(ready!=null);refresh.setEnabled(true);}});
        }},"SPDiagnosticExport").start();
    }

    private JSONArray exits(Map<String,byte[]> entries){
        JSONArray array=new JSONArray();
        if(Build.VERSION.SDK_INT<30)return array;
        try{
            ActivityManager manager=(ActivityManager)getSystemService(ACTIVITY_SERVICE);
            List<ApplicationExitInfo> list=manager.getHistoricalProcessExitReasons(getPackageName(),0,6);
            int traces=0;
            for(ApplicationExitInfo exit:list){
                JSONObject row=new JSONObject();row.put("pid",exit.getPid());row.put("process",exit.getProcessName());
                row.put("epochMs",exit.getTimestamp());row.put("reason",exit.getReason());row.put("status",exit.getStatus());
                row.put("pssKiBLastSample",exit.getPss());row.put("rssKiBLastSample",exit.getRss());row.put("importance",exit.getImportance());
                row.put("anrTraceAvailable",false);
                // Only ANR thread traces. Do not include native tombstone memory dumps or exception descriptions.
                if(exit.getReason()==ApplicationExitInfo.REASON_ANR && traces<2){
                    try(InputStream in=exit.getTraceInputStream()){
                        if(in!=null){
                            byte[] bytes=LogStore.readLimited(in,256000,true);
                            String path="system/anr-"+exit.getTimestamp()+".txt";
                            entries.put(path,bytes);row.put("anrTraceAvailable",true);row.put("traceFile",path);
                            row.put("tracePossiblyTruncated",bytes.length==256000);traces++;
                        }
                    }catch(Exception e){row.put("traceReadError",e.getClass().getSimpleName());}
                }
                array.put(row);
            }
        }catch(Exception ignored){}
        return array;
    }

    private String describe(Map<String,byte[]> entries,JSONObject meta)throws Exception{
        StringBuilder result=new StringBuilder("诊断版：").append(BuildInfo.BUILD).append("\n设备：").append(Build.MANUFACTURER).append(" ").append(Build.MODEL).append(" · Android ").append(Build.VERSION.RELEASE).append("\n");
        int count=0;
        for(String name:new String[]{"last-unfinished.jsonl","latest.jsonl","previous.jsonl"}){
            byte[] bytes=entries.get("loading/"+name);if(bytes==null)continue;
            String[] rows=new String(bytes,"UTF-8").split("\n");JSONObject first=null,last=null;
            for(String line:rows){try{JSONObject row=new JSONObject(line);if(first==null)first=row;last=row;}catch(JSONException ignored){}}
            if(first==null || last==null)continue;count++;
            result.append("\n").append(name.startsWith("last-")?"保留的未完成加载":name.startsWith("latest")?"最近一次加载":"前一次加载");
            result.append("\n时间：").append(new SimpleDateFormat("MM-dd HH:mm:ss",Locale.getDefault()).format(new Date(first.optLong("epochMs"))));
            result.append("\n最后记录：").append(last.optString("phase")).append(" / ").append(last.optString("edge"));
            result.append("\n已记录时段：").append(Math.max(0,last.optLong("ms")-first.optLong("ms"))).append(" ms\n");
        }
        if(count==0)result.append("\n尚无共斗加载记录。请先用本诊断版复现；当前文件仍含版本与可取得的退出信息。\n");
        result.append("\n系统退出记录：").append(meta.getJSONArray("exitHistory").length());
        if(Build.VERSION.SDK_INT<30)result.append("（此系统版本不支持读取退出历史）");
        String probe="尚未运行，请先启动一次游戏";
        try{byte[] raw=entries.get("loading/runtime.json");if(raw!=null)probe=BuildInfo.BUILD.equals(new JSONObject(new String(raw,"UTF-8")).optString("build"))?"已就绪":"旧版记录已保留，请启动本诊断版游戏";}catch(Exception ignored){}
        result.append("\n加载采集：").append(probe);
        result.append("\n“未完成”不等于已确认闪退原因，请一并告知发生时间和模式。");
        return result.toString();
    }

    private void share(){
        if(ready==null)return;
        try{
            Uri uri=new Uri.Builder().scheme("content").authority(getPackageName()+".loadingdiagnostics").appendPath(ready.getName()).build();
            Intent send=new Intent(Intent.ACTION_SEND);send.setType("application/zip");send.putExtra(Intent.EXTRA_STREAM,uri);
            send.setClipData(ClipData.newUri(getContentResolver(),"StarPoint loading diagnostics",uri));send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
            Intent chooser=Intent.createChooser(send,"发送诊断日志");chooser.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);startActivity(chooser);
        }catch(Exception e){status.setText(summary+"\n\n分享暂不可用，请用“保存到文件”或“复制诊断摘要”。");}
    }
    private void copySummary(){
        try{((ClipboardManager)getSystemService(CLIPBOARD_SERVICE)).setPrimaryClip(ClipData.newPlainText("StarPoint diagnostics",summary));Toast.makeText(this,"摘要已复制，可粘贴发送。完整分析请同时提供日志文件。",Toast.LENGTH_LONG).show();}
        catch(Exception e){status.setText(summary+"\n\n复制失败，请分享或保存日志文件。");}
    }
    private void saveDocument(){
        if(ready==null)return;
        if(Build.VERSION.SDK_INT>=29){saveDownload();return;}
        try{pendingExport=ready.getName();Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);intent.addCategory(Intent.CATEGORY_OPENABLE);intent.setType("application/zip");intent.putExtra(Intent.EXTRA_TITLE,pendingExport);intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_WRITE_URI_PERMISSION|Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);startActivityForResult(intent,SAVE_DOCUMENT);}
        catch(Exception e){pendingExport=null;status.setText(summary+"\n\n文件选择器不可用，请使用分享或复制。");}
    }
    private void copyTo(File source,Uri target)throws IOException{
        try(InputStream in=new FileInputStream(source);OutputStream out=getContentResolver().openOutputStream(target,"w")){
            if(out==null)throw new IOException("document unavailable");byte[] bytes=new byte[8192];int n;while((n=in.read(bytes))!=-1)out.write(bytes,0,n);
        }
    }
    private void saveDownload(){
        final File source=ready;busy=true;enable(false);
        new Thread(new Runnable(){public void run(){
            Uri created=null;String resultText;
            try{
                ContentValues values=new ContentValues();values.put(MediaStore.Downloads.DISPLAY_NAME,source.getName());
                values.put(MediaStore.Downloads.MIME_TYPE,"application/zip");values.put(MediaStore.Downloads.RELATIVE_PATH,"Download/StarPoint");values.put(MediaStore.Downloads.IS_PENDING,1);
                created=getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI,values);
                if(created==null)throw new IOException("download unavailable");copyTo(source,created);
                values.clear();values.put(MediaStore.Downloads.IS_PENDING,0);
                if(getContentResolver().update(created,values,null,null)!=1)throw new IOException("download commit");
                resultText="已保存到 下载/StarPoint/\n"+source.getName();
            }catch(Exception e){
                // Only the new, still-pending entry from this request can be removed on failure.
                if(created!=null)try{getContentResolver().delete(created,null,null);}catch(Exception ignored){}
                resultText="保存失败（"+e.getClass().getSimpleName()+"），请使用分享或重试。";
            }
            showSaveResult(resultText);
        }},"SPDiagnosticSave").start();
    }
    private void showSaveResult(final String message){
        runOnUiThread(new Runnable(){public void run(){if(isFinishing() || isDestroyed())return;busy=false;enable(ready!=null);refresh.setEnabled(true);status.setText(summary+"\n\n"+message);Toast.makeText(DiagnosticsActivity.this,message,Toast.LENGTH_LONG).show();}});
    }
    protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);
        if(request!=SAVE_DOCUMENT)return;
        if(result!=RESULT_OK || data==null || data.getData()==null){pendingExport=null;return;}
        final Uri target=data.getData();final File source;
        try{source=LogStore.exportFile(LogStore.inside(getCacheDir(),"cn-loading-diagnostic-exports"),pendingExport);}
        catch(Exception e){pendingExport=null;status.setText(summary+"\n\n保存中断，请重新点击“保存到文件”。");return;}
        pendingExport=null;busy=true;enable(false);
        new Thread(new Runnable(){public void run(){
            String resultText;
            try{
                copyTo(source,target);resultText="日志文件已保存。";
            }catch(Exception e){resultText="保存失败（"+e.getClass().getSimpleName()+"），请使用分享或重试。";}
            showSaveResult(resultText);
        }},"SPDiagnosticSave").start();
    }
}
