import unittest
from check_observables import compare

BASE="""define void @main() {
  %1 = call i1 @test.active()
  br i1 %1, label %2, label %7
; <label>:2
  %3 = call %dx.types.fouri32 @dx.op.waveActiveBallot(i32 116, i1 %1)
  %4 = extractvalue %dx.types.fouri32 %3, 0
  %5 = call %dx.types.fouri32 @dx.op.waveActiveBallot(i32 116, i1 true)
  call void @test.observable(i32 4)
  br label %8
; <label>:7
  br label %8
; <label>:8
  %9 = phi i32 [ %4, %2 ], [ 0, %7 ]
  call void @test.output(i32 %9)
  ret void
}
"""
CANDIDATE=BASE.replace("  %5 = call %dx.types.fouri32 @dx.op.waveActiveBallot(i32 116, i1 true)\n","")

class ObservableGraphTests(unittest.TestCase):
    def test_known_deletion_and_relabeling(self):
        renumbered=CANDIDATE.replace("%7","%42").replace("<label>:7","<label>:42")
        self.assertEqual(compare(BASE,renumbered)["blocks"],4)

    def test_control_operands_effects_and_order(self):
        effect="  call void @test.observable(i32 4)\n"
        before_vote="  %3 = call"
        changed=(
            CANDIDATE.replace("label %2, label %7","label %7, label %2"),
            CANDIDATE.replace("[ %4, %2 ], [ 0, %7 ]","[ %4, %7 ], [ 0, %2 ]"),
            CANDIDATE.replace("i32 116, i1 %1","i32 116, i1 true"),
            CANDIDATE.replace(effect,"").replace(before_vote,effect+before_vote),
        )
        for candidate in changed:
            with self.subTest(candidate=candidate),self.assertRaises(ValueError):
                compare(BASE,candidate)

if __name__=="__main__":
    unittest.main()
