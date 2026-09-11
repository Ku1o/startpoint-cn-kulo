import unittest
from types import SimpleNamespace as Obj
import prepare_content  # configure the existing MOD parser imports
import wf_rogue_bundle as b
from terrain_closure import bounded_action,nested_anchor_errors


class TerrainClosureTests(unittest.TestCase):
    def test_single_reference_point_keeps_one_callback_requirement(self):
        spawn=['Command',['SpawnFunnel',['Funnel','child'],8,['FunnelGroup',7],[]]]
        block=['Command',['CreateReferencePoint',-33,['AB'],0,0,0,False,False,['Single'],120,0,['Block',[spawn]]]]
        self.assertEqual(b._analyze_expression(bounded_action(block)).funnels['7'],8)
        block[1][8]=['Line',3,20,False]
        with self.assertRaisesRegex(ValueError,'unbounded command callback'):
            b._analyze_expression(bounded_action(block))

    def test_absent_nested_funnel_group_is_rejected_on_same_field(self):
        layer=Obj(layer='0',funnels=[],spawned_refs=[b.SpawnedRef('Funnel','interface')])
        cap=Obj(custom_positions=[],funnel_groups=[])
        receipts={'Funnel|interface|100':{'positions':[],'funnels':{'7':8},'references':[]}}
        self.assertIn('missing FUNNEL_SPAWN7',nested_anchor_errors(layer,cap,receipts)[0])
        cap.funnel_groups=[('7',8)]
        self.assertEqual(nested_anchor_errors(layer,cap,receipts),[])

    def test_primary_missing_group_is_also_rejected(self):
        layer=Obj(layer='0',funnels=[b.FunnelRequirement('6',2,())],spawned_refs=[])
        cap=Obj(custom_positions=[],funnel_groups=[])
        self.assertIn('missing FUNNEL_SPAWN6',nested_anchor_errors(layer,cap,{})[0])


if __name__=='__main__':unittest.main()
