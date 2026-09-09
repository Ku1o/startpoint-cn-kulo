import copy,unittest
import optimize_battle_atlases as opt
import wf_battle_atlas_repack as a
from validate_lens0909_completion import verify_pair
from PIL import Image

class AtlasCompactionTests(unittest.TestCase):
    def source(self):
        im=Image.new('RGBA',(256,128))
        crop=Image.new('RGBA',(8,12));crop.paste((241,21,3,127),(2,3,7,10))
        im.paste(crop,(5,5));im.paste(crop,(105,65))
        frames=[{'n':'frame0001','x':5,'y':5,'w':8,'h':12,'r':True,'fx':-4,'fy':-5,'fw':20,'fh':20},
                {'n':'frame0002','x':105,'y':65,'w':8,'h':12,'r':True,'fx':-1,'fy':-3,'fw':20,'fh':20},
                {'n':'frame0003','x':140,'y':80,'w':12,'h':12}]
        return a.encode_png(im),a.encode_atlas(frames)

    def test_duplicate_pixels_with_distinct_offsets_rotated_trim_and_empty_frame(self):
        png,atlas=self.source();out_png,out_atlas,receipt=opt.optimize(png,atlas)
        self.assertEqual(verify_pair(png,atlas,out_png,out_atlas),3)
        self.assertLess(receipt['after_area'],receipt['before_area'])
        rows=a.decode_atlas(out_atlas)
        self.assertEqual((rows[0]['x'],rows[0]['y']),(rows[1]['x'],rows[1]['y']))
        self.assertNotEqual(rows[0]['fx'],rows[1]['fx'])

    def test_rejects_removed_frame_wrong_offset_and_plain_png(self):
        png,atlas=self.source();out_png,out_atlas,_=opt.optimize(png,atlas)
        rows=a.decode_atlas(out_atlas)
        with self.assertRaises(AssertionError):verify_pair(png,atlas,out_png,a.encode_atlas(rows[:-1]))
        broken=copy.deepcopy(rows);broken[0]['fx']-=1
        with self.assertRaises(AssertionError):verify_pair(png,atlas,out_png,a.encode_atlas(broken))
        with self.assertRaises(AssertionError):verify_pair(png,atlas,opt.p.wf_assets.png_decode_stored(out_png),out_atlas)

if __name__=='__main__':unittest.main()
