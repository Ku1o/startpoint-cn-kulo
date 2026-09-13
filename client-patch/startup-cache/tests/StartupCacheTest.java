package cn.startpoint;
import java.io.*;
import java.nio.file.*;
import java.util.*;

public final class StartupCacheTest {
    static void put(File f) throws Exception {f.getParentFile().mkdirs();Files.write(f.toPath(),new byte[]{1,2,3});}
    static void check(boolean value) {if(!value)throw new AssertionError();}
    public static void main(String[] args) throws Exception {
        File base=Files.createTempDirectory("sp-startup-cache-test-").toFile();
        File root=new File(base,"com.leiting.wf");root.mkdir();
        File apk=new File(base,"base.apk");put(apk);
        File cached=new File(root,"cache/app/old/assets/game.swf"), air=new File(root,"cache/.AIR/cookies");
        File[] kept={new File(root,"com.leiting.wf/Local Store/asset/data"),
            new File(root,"com.leiting.wf/Local Store/custom_Release_Android/application_option"),
            new File(root,"files/account"),new File(root,"shared_prefs/login"),new File(root,"cache/oat_primary/native")};
        for(File f:kept)put(f);put(cached);put(air);
        StartupCache.clean(root,apk,"payload-1");check(!cached.exists()&&!air.exists());
        for(File f:kept)check(Arrays.equals(Files.readAllBytes(f.toPath()),new byte[]{1,2,3}));
        put(cached);StartupCache.clean(root,apk,"payload-1");check(cached.exists());
        check(apk.setLastModified(apk.lastModified()+10000));
        StartupCache.clean(root,apk,"payload-1");check(!cached.exists());
        put(cached);StartupCache.clean(root,apk,"payload-2");check(!cached.exists());
        // Failed marker write must not acknowledge the installation. Next launch retries.
        File next=new File(root,"no_backup/sp-startup-cache.next");check(next.mkdir());
        boolean failed=false;try{StartupCache.clean(root,apk,"payload-3");}catch(IOException expected){failed=true;}
        check(failed);check(next.delete());put(cached);
        StartupCache.clean(root,apk,"payload-3");check(!cached.exists());
        for(File f:kept)check(f.exists());
        // Delete only the verified JVM-created temporary fixture.
        check(base.getCanonicalFile().getParentFile().equals(new File(System.getProperty("java.io.tmpdir")).getCanonicalFile()));
        try(java.util.stream.Stream<Path> paths=Files.walk(base.toPath())) {
            for(Path p:(Iterable<Path>)paths.sorted(Comparator.reverseOrder())::iterator)Files.delete(p);
        }
        System.out.println("PASS first install, repeat launch, same-payload reinstall, new payload, retry, protected data");
        System.exit(0);
    }
}
