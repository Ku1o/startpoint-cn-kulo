package cn.startpoint;

import android.content.pm.ApplicationInfo;
import android.os.Process;
import android.util.Log;
import java.io.*;
import java.nio.channels.FileLock;

/** Runs before the packed AIR loader. Never visits Local Store, files or preferences. */
public final class StartupCache {
    private static final String TAG = "SPStartupCache";

    public static void run(ApplicationInfo info) {
        try {
            if (info == null || !"com.leiting.wf".equals(info.packageName)
                    || info.uid != Process.myUid()) return;
            clean(new File(info.dataDir), new File(info.sourceDir), BuildIdentity.ID);
        } catch (Exception error) {
            // A transient cleanup failure must not prevent starting the game; retry next launch.
            Log.w(TAG, "cleanup deferred: " + error.getClass().getSimpleName());
        }
    }

    static void clean(File data, File apk, String build) throws IOException {
        File root = data.getCanonicalFile();
        if (!root.isDirectory() || !"com.leiting.wf".equals(root.getName()) || !apk.isFile())
            throw new IOException("invalid application directories");
        File stateDir = inside(root, "no_backup");
        if (!stateDir.isDirectory() && !stateDir.mkdir()) throw new IOException("state directory");
        // PackageInstaller replaces the APK path and/or mtime even for a same-version cover install.
        // The payload ID also handles different SWFs with the same public application version.
        String stamp = "v1\n" + build + "\n" + apk.getAbsolutePath() + "\n"
                + apk.lastModified() + "\n" + apk.length() + "\n";
        File lockFile = inside(stateDir, "sp-startup-cache.lock");
        try (RandomAccessFile lock = new RandomAccessFile(lockFile, "rw");
             FileLock held = lock.getChannel().lock()) {
            File marker = inside(stateDir, "sp-startup-cache.state");
            if (stamp.equals(read(marker))) {
                Log.i(TAG, "unchanged installation; skipped");
                return;
            }
            File cache = inside(root, "cache");
            // Exact AIR startup allowlist. Downloaded assets live outside this directory.
            boolean cleared = remove(inside(cache, "app"));
            cleared = remove(inside(cache, ".AIR")) && cleared;
            if (!cleared) throw new IOException("incomplete cleanup");
            File next = inside(stateDir, "sp-startup-cache.next");
            try (FileOutputStream output = new FileOutputStream(next)) {
                output.write(stamp.getBytes("UTF-8"));
                output.getFD().sync();
            }
            if (!next.renameTo(marker)) throw new IOException("commit marker");
            Log.i(TAG, "installation changed; AIR startup cache cleared");
        }
    }

    private static String read(File file) throws IOException {
        if (!file.isFile() || file.length() > 4096) return "";
        ByteArrayOutputStream data = new ByteArrayOutputStream();
        try (FileInputStream input = new FileInputStream(file)) {
            byte[] bytes = new byte[512];
            int count;
            while ((count = input.read(bytes)) != -1) {
                data.write(bytes, 0, count);
                if (data.size() > 4096) return "";
            }
        }
        return data.toString("UTF-8");
    }

    private static File inside(File parent, String name) throws IOException {
        File file = new File(parent, name).getAbsoluteFile();
        if (!file.getCanonicalFile().equals(file)) throw new IOException("symlink outside allowlist");
        return file;
    }

    private static boolean remove(File file) throws IOException {
        if (!file.exists()) return true;
        if (!file.getCanonicalFile().equals(file.getAbsoluteFile()))
            throw new IOException("symlink inside cache");
        boolean done = true;
        if (file.isDirectory()) {
            File[] children = file.listFiles();
            if (children == null) return false;
            for (File child : children) done = remove(child) && done;
        }
        return done && file.delete();
    }
}
