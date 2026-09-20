import cn.startpoint.diagnostics.LogStore;
import java.io.*;
import java.nio.file.*;
import java.util.*;
import java.util.zip.*;

public class LogStoreTest {
    static int checks=0;
    static void check(boolean value,String message){checks++;if(!value)throw new AssertionError(message);}
    interface Op {void run()throws Exception;}
    static void rejects(Op action)throws Exception{boolean failed=false;try{action.run();}catch(IOException e){failed=true;}check(failed,"negative case was accepted");}
    public static void main(String[] args)throws Exception{
        final File root=new File(args[0]);root.mkdirs();
        final File data=new File(root,"com.leiting.wf");data.mkdirs();
        check(LogStore.findAirDirectory(data,"com.leiting.wf")==null,"no fabricated AIR folder");
        File dir=new File(data,"app_storage/com.leiting.wf/Local Store/cn-loading-diagnostics");dir.mkdirs();
        check(LogStore.findAirDirectory(data,"com.leiting.wf").equals(dir.getCanonicalFile()),"AIR directory discovery");
        byte[] unfinished="{\"phase\":\"rect.pack\",\"edge\":\"begin\"}\n".getBytes("UTF-8");
        Files.write(new File(dir,"last-unfinished.jsonl").toPath(),unfinished);
        Files.write(new File(dir,"latest.jsonl").toPath(),"{\"phase\":\"session.complete\"}\n".getBytes("UTF-8"));
        Files.write(new File(dir,"account-secret.txt").toPath(),"never export this".getBytes("UTF-8"));
        Map<String,byte[]> map=LogStore.snapshot(dir);
        check(map.size()==2,"exact file allowlist");
        check(Arrays.equals(unfinished,map.get("loading/last-unfinished.jsonl")),"unfinished survives later complete record");
        Files.write(new File(dir,"previous.jsonl").toPath(),new byte[LogStore.MAX_LOG+1]);
        check(LogStore.snapshot(dir).containsKey("loading/previous.jsonl.unavailable.txt"),"oversize fail bounded");
        final File exports=new File(root,"exports");exports.mkdirs();
        rejects(new Op(){public void run()throws Exception{LogStore.exportFile(exports,"../latest.jsonl");}});
        rejects(new Op(){public void run()throws Exception{LogStore.exportFile(exports,"StarPoint-Loading-1.zip/../../secret");}});
        rejects(new Op(){public void run()throws Exception{LogStore.inside(root,"../escape");}});
        File zip=LogStore.exportFile(exports,"StarPoint-Loading-20260913-1.zip");
        LogStore.writeZip(zip,map);
        try(ZipFile z=new ZipFile(zip)){
            check(z.size()==2,"zip allowlist");
            check(Arrays.equals(unfinished,LogStore.readLimited(z.getInputStream(z.getEntry("loading/last-unfinished.jsonl")),1000,false)),"complete archive readback");
        }
        check(LogStore.readLimited(new ByteArrayInputStream(new byte[13]),12,true).length==12,"stream truncation");
        rejects(new Op(){public void run()throws Exception{LogStore.readLimited(new ByteArrayInputStream(new byte[13]),12,false);}});
        for(int i=2;i<11;i++){File f=LogStore.exportFile(exports,"StarPoint-Loading-20260913-"+i+".zip");Files.write(f.toPath(),new byte[]{1});f.setLastModified(100000L+i);}
        LogStore.trimExports(exports,zip);
        check(zip.exists(),"currently shared export preserved");
        check(exports.listFiles().length<=7,"bounded previous exports");
        check(new File(dir,"account-secret.txt").isFile(),"unrelated file untouched");
        check(Arrays.equals(Files.readAllBytes(new File(dir,"last-unfinished.jsonl").toPath()),unfinished),"source diagnostics not mutated by export");
        File actual33=new File(data,"com.leiting.wf/Local Store/cn-loading-diagnostics");actual33.mkdirs();
        check(LogStore.findAirDirectory(data,"com.leiting.wf").equals(actual33.getCanonicalFile()),"AIR 33 application-id directory preferred");
        System.out.println("LOG_STORE_TESTS_PASSED "+checks);
    }
}
