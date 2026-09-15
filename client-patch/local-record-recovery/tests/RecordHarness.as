package {
    import cn.storage.LocalRecordIO;
    import flash.filesystem.File;
    import flash.filesystem.FileMode;
    import flash.filesystem.FileStream;
    import flash.utils.ByteArray;
    public final class RecordHarness {
        public static function run(root:File):Object {
            if(root.exists)throw new Error("Fixture path must be new.");
            root.createDirectory();
            var checks:Array=[],file:File=root.resolvePath("account");
            function data(s:String):ByteArray {var b:ByteArray=new ByteArray();b.writeUTFBytes(s);return b;}
            function read():String {var f:FileStream=new FileStream();f.open(file,FileMode.READ);var s:String=f.readUTFBytes(f.bytesAvailable);f.close();return s;}
            function check(ok:Boolean,label:String):void {if(!ok)throw new Error(label);checks.push(label);}
            LocalRecordIO.writeBinaryFile(file,{b:data("first complete record")});
            check(read()=="first complete record","new record bytes");
            var next:ByteArray=data("second complete record");next.position=3;
            LocalRecordIO.writeBinaryFile(file,{b:next});
            check(read()=="second complete record","replacement writes all bytes from offset zero");
            check(next.position==3,"input position preserved");
            var failed:Boolean=false;
            try {LocalRecordIO.writeBinaryFile(file,{b:new ByteArray()});}catch(e:*){failed=true;}
            check(failed && read()=="second complete record","empty payload preserves previous record");
            var pending:File=root.resolvePath("account.sp-write"),stream:FileStream=new FileStream();
            stream.open(pending,FileMode.WRITE);stream.close();
            check(read()=="second complete record","interrupted empty temporary file leaves old record readable");
            LocalRecordIO.writeBinaryFile(file,{b:data("third complete record")});
            check(read()=="third complete record" && !pending.exists,"retry replaces stale temporary file");
            pending.createDirectory();var marker:File=pending.resolvePath("marker");
            stream.open(marker,FileMode.WRITE);stream.writeUTFBytes("keep");stream.close();failed=false;
            try {LocalRecordIO.writeBinaryFile(file,{b:data("must not replace")});}catch(e:*){failed=true;}
            check(failed && read()=="third complete record" && marker.exists,"write failure preserves old file and unrelated directory contents");
            marker.deleteFile();pending.deleteDirectory();
            LocalRecordIO.writeBinaryFile(file,{b:data("recovered after failure")});
            check(read()=="recovered after failure","valid write succeeds after transient failure");
            return {ok:true,checks:checks,fixture:root.nativePath};
        }
    }
}
