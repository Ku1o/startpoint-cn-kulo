package cn.startpoint.diagnostics;

import java.io.*;
import java.util.*;
import java.util.zip.*;

/** Narrow diagnostic-file allowlist; never walks saves, preferences or game assets. */
public final class LogStore {
    public static final String[] NAMES = {"runtime.json", "latest.jsonl", "previous.jsonl", "last-unfinished.jsonl"};
    public static final int MAX_LOG = 160000;

    public static File inside(File parent, String child) throws IOException {
        File root = parent.getCanonicalFile();
        File result = new File(root, child).getCanonicalFile();
        if (!result.getPath().startsWith(root.getPath() + File.separator)) throw new IOException("path boundary");
        return result;
    }

    public static File findAirDirectory(File data, String packageName) throws IOException {
        File root = data.getCanonicalFile();
        List<File> bases = new ArrayList<File>();
        // AIR 33 uses <dataDir>/<applicationId>/Local Store; the descriptor id is com.leiting.wf.
        bases.add(inside(root, packageName + "/Local Store"));
        bases.add(inside(root, "app_storage/" + packageName + "/Local Store"));
        bases.add(inside(root, "app_storage/Local Store"));
        bases.add(inside(root, "files/Local Store"));
        File storage = inside(root, "app_storage");
        File[] children = storage.listFiles();
        if (children != null && children.length <= 32) {
            for (File child : children) {
                if (child.getName().matches("[A-Za-z0-9._-]{1,96}"))
                    bases.add(inside(root, "app_storage/" + child.getName() + "/Local Store"));
            }
        }
        for (File base : bases) {
            File d = inside(base, "cn-loading-diagnostics");
            if (d.isDirectory()) return d;
        }
        return null;
    }

    public static byte[] readLimited(File file, int limit) throws IOException {
        if (!file.isFile() || file.length() > limit) throw new IOException("file missing or oversized");
        try (InputStream input = new FileInputStream(file)) {
            return readLimited(input, limit, false);
        }
    }

    public static byte[] readLimited(InputStream input, int limit, boolean truncate) throws IOException {
        ByteArrayOutputStream output = new ByteArrayOutputStream();
        byte[] bytes = new byte[8192];
        int count;
        while ((count = input.read(bytes, 0, Math.min(bytes.length, limit + 1 - output.size()))) != -1) {
            output.write(bytes, 0, count);
            if (output.size() > limit) {
                if (truncate) return Arrays.copyOf(output.toByteArray(), limit);
                throw new IOException("read limit");
            }
        }
        return output.toByteArray();
    }

    public static Map<String, byte[]> snapshot(File directory) throws IOException {
        Map<String, byte[]> files = new LinkedHashMap<String, byte[]>();
        if (directory == null) return files;
        for (String name : NAMES) {
            File f = inside(directory, name);
            if (!f.exists()) continue;
            try { files.put("loading/" + name, readLimited(f, MAX_LOG)); }
            catch (IOException e) { files.put("loading/" + name + ".unavailable.txt", "Record unavailable or exceeds diagnostic limit.\n".getBytes("UTF-8")); }
        }
        return files;
    }

    public static File exportFile(File directory, String name) throws IOException {
        if (name == null || !name.matches("StarPoint-Loading-[0-9-]+\\.zip")) throw new IOException("invalid export name");
        return inside(directory, name);
    }

    public static void writeZip(File target, Map<String, byte[]> files) throws IOException {
        if (!target.getParentFile().isDirectory() && !target.getParentFile().mkdirs()) throw new IOException("export directory");
        File temp = new File(target.getParentFile(), target.getName() + ".tmp");
        try (ZipOutputStream out = new ZipOutputStream(new FileOutputStream(temp))) {
            for (Map.Entry<String, byte[]> entry : files.entrySet()) {
                if (!entry.getKey().matches("[A-Za-z0-9_./-]+") || entry.getKey().contains("..") || entry.getKey().startsWith("/"))
                    throw new IOException("zip path");
                out.putNextEntry(new ZipEntry(entry.getKey())); out.write(entry.getValue()); out.closeEntry();
            }
        }
        if (!temp.renameTo(target)) throw new IOException("export commit");
    }

    public static void trimExports(File directory, File keep) {
        File[] found = directory.listFiles();
        if (found == null) return;
        List<File> list = new ArrayList<File>();
        for (File f : found) if (f.isFile() && f.getName().matches("StarPoint-Loading-[0-9-]+\\.zip")) list.add(f);
        Collections.sort(list, new Comparator<File>() { public int compare(File a, File b) { return Long.compare(b.lastModified(), a.lastModified()); } });
        // Keep several exports so a recipient can finish reading an earlier granted URI.
        for (int i=6; i<list.size(); i++) {
            File file=list.get(i);
            try { if (!file.equals(keep) && file.getCanonicalFile().equals(new File(directory.getCanonicalFile(),file.getName()))) file.delete(); }
            catch(IOException ignored) {}
        }
    }
}
