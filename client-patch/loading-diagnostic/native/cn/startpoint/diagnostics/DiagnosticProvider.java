package cn.startpoint.diagnostics;

import android.content.ContentProvider;
import android.content.ContentValues;
import android.database.Cursor;
import android.database.MatrixCursor;
import android.net.Uri;
import android.os.ParcelFileDescriptor;
import android.provider.OpenableColumns;
import java.io.*;

/** Non-exported provider: the share intent grants read access to one generated ZIP only. */
public final class DiagnosticProvider extends ContentProvider {
    public boolean onCreate() { return true; }

    private File file(Uri uri) throws FileNotFoundException {
        try {
            if (!"content".equals(uri.getScheme()) || !getContext().getPackageName().concat(".loadingdiagnostics").equals(uri.getAuthority())
                    || uri.getPathSegments().size()!=1 || uri.getQuery()!=null || uri.getFragment()!=null)
                throw new IOException("invalid diagnostic URI");
            File root=LogStore.inside(getContext().getCacheDir(),"cn-loading-diagnostic-exports");
            File result=LogStore.exportFile(root,uri.getLastPathSegment());
            if (!result.isFile() || result.length()>1200000) throw new IOException("export unavailable");
            return result;
        } catch(IOException e) {throw new FileNotFoundException("Diagnostic export unavailable");}
    }
    public String getType(Uri uri) {return "application/zip";}
    public ParcelFileDescriptor openFile(Uri uri,String mode) throws FileNotFoundException {
        if (!"r".equals(mode)) throw new FileNotFoundException("Read-only diagnostic export");
        return ParcelFileDescriptor.open(file(uri),ParcelFileDescriptor.MODE_READ_ONLY);
    }
    public Cursor query(Uri uri,String[] projection,String selection,String[] args,String sort) {
        try {
            File f=file(uri);
            String[] cols=projection==null?new String[]{OpenableColumns.DISPLAY_NAME,OpenableColumns.SIZE}:projection;
            MatrixCursor c=new MatrixCursor(cols,1);Object[] row=new Object[cols.length];
            for(int i=0;i<cols.length;i++) {
                if(OpenableColumns.DISPLAY_NAME.equals(cols[i]))row[i]=f.getName();
                else if(OpenableColumns.SIZE.equals(cols[i]))row[i]=f.length();
            }
            c.addRow(row);return c;
        } catch(FileNotFoundException e) {return null;}
    }
    public Uri insert(Uri u,ContentValues v) {throw new UnsupportedOperationException("read only");}
    public int update(Uri u,ContentValues v,String s,String[] a) {throw new UnsupportedOperationException("read only");}
    public int delete(Uri u,String s,String[] a) {throw new UnsupportedOperationException("read only");}
}
