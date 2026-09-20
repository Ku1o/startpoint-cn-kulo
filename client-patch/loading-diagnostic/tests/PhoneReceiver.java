package cn.startpoint.diagnosticqa;

import android.app.Activity;
import android.content.*;
import android.net.Uri;
import android.os.Bundle;
import android.widget.TextView;
import java.io.*;
import java.util.*;
import java.util.zip.*;
import org.json.*;

/** Separate local-only QA app. Never included in the delivered game APK. */
public final class PhoneReceiver extends Activity {
    public void onWindowFocusChanged(boolean focused){super.onWindowFocusChanged(focused);if(!focused)return;
        try{File file=new File(getFilesDir(),"report.json");if(!file.isFile())return;
            JSONObject report=new JSONObject(read(new FileInputStream(file)));
            ClipboardManager clipboard=(ClipboardManager)getSystemService(CLIPBOARD_SERVICE);ClipData clip=clipboard.getPrimaryClip();
            String copied=clip==null?"":String.valueOf(clip.getItemAt(0).getText());report.put("diagnosticSummaryOnClipboard",copied.startsWith("诊断版：CN-LOAD-"));
            try(OutputStream out=new FileOutputStream(file)){out.write(report.toString(2).getBytes("UTF-8"));}
        }catch(Exception ignored){}
    }
    protected void onCreate(Bundle state){super.onCreate(state);TextView view=new TextView(this);view.setTextSize(20);view.setPadding(24,48,24,24);setContentView(view);
        try{
            Uri uri=getIntent().getParcelableExtra(Intent.EXTRA_STREAM);if(uri==null)throw new IOException("no shared URI");
            File zip=new File(getFilesDir(),"received.zip");
            try(InputStream in=getContentResolver().openInputStream(uri);OutputStream out=new FileOutputStream(zip)){
                byte[] buffer=new byte[8192];int n,total=0;while((n=in.read(buffer))!=-1){total+=n;if(total>1200000)throw new IOException("share bound");out.write(buffer,0,n);}
            }
            JSONObject report=new JSONObject();JSONArray names=new JSONArray();
            try(ZipFile z=new ZipFile(zip)){
                Enumeration<? extends ZipEntry> list=z.entries();while(list.hasMoreElements())names.put(list.nextElement().getName());
                report.put("metadata",new JSONObject(read(z.getInputStream(z.getEntry("metadata.json")))));
                ZipEntry runtime=z.getEntry("loading/runtime.json");if(runtime!=null)report.put("runtime",new JSONObject(read(z.getInputStream(runtime))));
            }
            report.put("members",names);report.put("zipBytes",zip.length());
            boolean denied=false;try{getContentResolver().openFileDescriptor(uri,"w").close();}catch(Exception e){denied=true;}
            report.put("writeDenied",denied);if(!denied)throw new IOException("provider is not read-only");
            ClipboardManager clipboard=(ClipboardManager)getSystemService(CLIPBOARD_SERVICE);
            ClipData clip=clipboard.getPrimaryClip();String copied=clip==null?"":String.valueOf(clip.getItemAt(0).getText());
            report.put("diagnosticSummaryOnClipboard",copied.startsWith("诊断版：CN-LOAD-"));
            try(OutputStream out=new FileOutputStream(new File(getFilesDir(),"report.json"))){out.write(report.toString(2).getBytes("UTF-8"));}
            view.setText("本机导出测试通过\nZIP 字节："+zip.length()+"\n成员："+names+"\n接收方无写权限："+denied);
        }catch(Exception e){view.setText("导出测试失败："+e.getClass().getSimpleName());}
    }
    private String read(InputStream input)throws Exception{try(InputStream in=input;ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[4096];int n;while((n=in.read(b))!=-1){if(out.size()+n>20000)throw new IOException("metadata bound");out.write(b,0,n);}return out.toString("UTF-8");}}
}
