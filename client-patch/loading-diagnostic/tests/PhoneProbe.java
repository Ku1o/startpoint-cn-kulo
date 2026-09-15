package cn.startpoint.diagnosticqa;

import android.app.Instrumentation;
import android.app.Activity;
import android.content.Context;
import android.os.Bundle;
import java.io.*;
import java.util.*;
import org.json.*;

/** Explicit fixture operations in the new diagnostic directory only; no game saves or accounts. */
public final class PhoneProbe extends Instrumentation {
    private String operation;
    private static final String[] NAMES={"runtime.json","latest.jsonl","previous.jsonl","last-unfinished.jsonl"};
    public void onCreate(Bundle args){operation=args.getString("op","inspect");start();}
    public void onStart(){Bundle reply=new Bundle();
        try{
            Context ctx=getTargetContext();File data=new File(ctx.getApplicationInfo().dataDir);
            File dir=new File(data,"com.leiting.wf/Local Store/cn-loading-diagnostics");
            File backup=new File(data,"cn-loading-diagnostic-qa-backup");
            if("seed".equals(operation)){
                if(backup.exists())throw new IOException("backup already exists");if(!dir.isDirectory())throw new IOException("start game first");
                if(!backup.mkdir())throw new IOException("backup directory");
                for(String name:NAMES){File f=new File(dir,name);if(f.exists())copy(f,new File(backup,name));}
                long now=System.currentTimeMillis();
                write(new File(dir,"latest.jsonl"),"{\"phase\":\"session.begin\",\"edge\":\"point\",\"ms\":100,\"epochMs\":"+now+",\"qaFixture\":true}\n{\"phase\":\"rect.pack\",\"edge\":\"begin\",\"ms\":200,\"epochMs\":"+now+",\"qaFixture\":true}\n");
                write(new File(dir,"last-unfinished.jsonl"),"{\"phase\":\"atlas.draw\",\"edge\":\"begin\",\"ms\":321,\"epochMs\":"+now+",\"qaFixture\":true}\n");
                write(new File(dir,"never-export-qa.txt"),"must not be exported");
            }else if("restore".equals(operation)){
                if(!backup.isDirectory())throw new IOException("no QA backup");
                for(String name:NAMES){File saved=new File(backup,name),target=new File(dir,name);if(saved.exists()){copy(saved,target);if(!saved.delete())throw new IOException("backup cleanup");}else if(target.exists()){String text=read(target);if(!text.contains("qaFixture"))throw new IOException("not a QA fixture");if(!target.delete())throw new IOException("fixture cleanup");}}
                File sentinel=new File(dir,"never-export-qa.txt");if(sentinel.exists() && !sentinel.delete())throw new IOException("sentinel cleanup");
                if(!backup.delete())throw new IOException("backup not empty");
            }else if(!"inspect".equals(operation))throw new IOException("unknown operation");
            JSONObject report=new JSONObject();report.put("op",operation);report.put("directoryExists",dir.isDirectory());
            JSONObject files=new JSONObject();for(String name:NAMES){File f=new File(dir,name);if(f.isFile()){files.put(name,f.length());if(name.equals("runtime.json"))report.put("runtime",new JSONObject(read(f)));}}
            report.put("files",files);reply.putString("report",report.toString());finish(Activity.RESULT_OK,reply);
        }catch(Exception e){reply.putString("failure",e.getClass().getSimpleName()+": "+e.getMessage());finish(Activity.RESULT_CANCELED,reply);}
    }
    private static String read(File file)throws Exception{if(file.length()>160000)throw new IOException("bound");try(InputStream in=new FileInputStream(file);ByteArrayOutputStream out=new ByteArrayOutputStream()){byte[] b=new byte[8192];int n;while((n=in.read(b))!=-1){if(out.size()+n>160000)throw new IOException("read bound");out.write(b,0,n);}return out.toString("UTF-8");}}
    private static void write(File file,String text)throws Exception{try(OutputStream out=new FileOutputStream(file)){out.write(text.getBytes("UTF-8"));}}
    private static void copy(File from,File to)throws Exception{write(to,read(from));}
}
