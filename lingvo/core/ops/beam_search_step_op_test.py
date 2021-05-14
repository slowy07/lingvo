# Lint as: python3
# Copyright 2018 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Tests for beam_search_op."""

from absl.testing import parameterized
from lingvo import compat as tf
from lingvo.core import ops
from lingvo.core import test_utils
from lingvo.core.ops import hyps_pb2
import numpy as np

from google.protobuf import text_format

_MIN_SCORE = -1e36


class BeamSearchOpTest(test_utils.TestCase, parameterized.TestCase):

  def setUp(self):
    super().setUp()
    np.random.seed(12345)
    tf.random.set_seed(398849988)

  def _runBeamSearchOpHelper(self,
                             hyp_size,
                             num_beams,
                             seq_len,
                             init_best_score,
                             probs,
                             init_atten_probs,
                             atten_probs,
                             beam_size=3.0,
                             ensure_full_beam=False,
                             force_eos_in_last_step=False,
                             local_eos_threshold=-100.0,
                             independence=True,
                             use_v2=True):
    eos_id = 2
    num_hyps_per_beam = hyp_size / num_beams

    best_scores = tf.zeros([num_beams])
    cumulative_scores = tf.zeros([hyp_size])
    scores = tf.zeros([seq_len, hyp_size])
    hyps = tf.zeros([seq_len, hyp_size], dtype=tf.int32)
    prev_hyps = tf.zeros([seq_len, hyp_size], dtype=tf.int32)
    done_hyps = tf.constant('', shape=[seq_len, hyp_size], dtype=tf.string)
    best_scores += init_best_score
    beam_done = tf.zeros([num_beams], dtype=tf.bool)

    for i, prob in enumerate(probs):
      if use_v2:
        (best_scores, cumulative_scores, scores, hyps, prev_hyps, done_hyps,
         atten_probs, beam_done, done) = ops.beam_search_step_v2(
             prob,
             init_atten_probs,
             best_scores,
             cumulative_scores,
             scores,
             hyps,
             prev_hyps,
             done_hyps,
             atten_probs,
             beam_done, [],
             i,
             eos_id=eos_id,
             beam_size=beam_size,
             ensure_full_beam=ensure_full_beam,
             num_hyps_per_beam=num_hyps_per_beam,
             valid_eos_max_logit_delta=0.1,
             force_eos_in_last_step=force_eos_in_last_step,
             local_eos_threshold=local_eos_threshold,
             beam_independence=independence)
      else:
        (best_scores, cumulative_scores, scores, hyps, prev_hyps, done_hyps,
         atten_probs, done) = ops.beam_search_step(
             prob,
             init_atten_probs,
             best_scores,
             cumulative_scores,
             scores,
             hyps,
             prev_hyps,
             done_hyps,
             atten_probs, [],
             i,
             eos_id=eos_id,
             beam_size=beam_size,
             ensure_full_beam=ensure_full_beam,
             num_hyps_per_beam=num_hyps_per_beam,
             valid_eos_max_logit_delta=0.1,
             force_eos_in_last_step=force_eos_in_last_step,
             local_eos_threshold=local_eos_threshold)

    with self.session(use_gpu=False):
      (best_scores, cumulative_scores, scores, hyps, prev_hyps, done_hyps,
       atten_probs, done, beam_done) = self.evaluate([
           best_scores, cumulative_scores, scores, hyps, prev_hyps, done_hyps,
           atten_probs, done, beam_done
       ])

    return (best_scores, cumulative_scores, scores, hyps, prev_hyps, done_hyps,
            atten_probs, done, beam_done)

  def _testBeamSearchOpHelper(self,
                              hyp_size,
                              num_beams,
                              seq_len,
                              init_best_score,
                              probs,
                              init_atten_probs,
                              atten_probs,
                              best_scores_expected,
                              cum_scores_expected,
                              scores_expected,
                              hyps_expected,
                              prev_hyps_expected,
                              atten_probs_expected,
                              force_eos_in_last_step=False,
                              local_eos_threshold=-100.0,
                              use_v2=True):

    (best_scores, cumulative_scores, scores, hyps, prev_hyps, done_hyps,
     atten_probs, done, beam_done) = self._runBeamSearchOpHelper(
         hyp_size,
         num_beams,
         seq_len,
         init_best_score,
         probs,
         init_atten_probs,
         atten_probs,
         force_eos_in_last_step=force_eos_in_last_step,
         local_eos_threshold=local_eos_threshold,
         use_v2=use_v2)

    tf.logging.info(np.array_repr(best_scores))
    tf.logging.info(np.array_repr(cumulative_scores))
    tf.logging.info(np.array_repr(scores))
    tf.logging.info(np.array_repr(hyps))
    tf.logging.info(np.array_repr(prev_hyps))
    tf.logging.info(np.array_repr(done_hyps))
    tf.logging.info(np.array_repr(atten_probs))
    tf.logging.info(np.array_repr(done))
    tf.logging.info(np.array_repr(scores))
    tf.logging.info(np.array_repr(atten_probs))

    self.assertAllClose(best_scores_expected, best_scores)
    self.assertAllClose(cum_scores_expected, cumulative_scores)
    self.assertAllClose(scores_expected, scores)
    self.assertAllClose(hyps_expected, hyps)
    self.assertAllClose(prev_hyps_expected, prev_hyps)
    self.assertAllClose(atten_probs_expected, atten_probs)

    self.assertEqual(False, done)
    expected_beam_done = np.array([False] * num_beams)
    self.assertAllEqual(expected_beam_done, beam_done)

    return done_hyps

  @parameterized.parameters(False, True)
  def testBeamSearchOp(self, use_v2):
    hyp_size = 8
    num_beams = 2
    seq_len = 6
    num_classes = 5

    best_scores_expected = [1.769434, 1.640316]
    cum_scores_expected = [
        1.823942, 1.609159, 1.610366, 1.454234, 1.348811, 1.3167, 1.346274,
        1.045735
    ]
    scores_expected = [
        [
            0.86230338, 0.84442794, 0.45372832, 0.38127339, 0.42067075,
            0.25818801, 0.38612545, 0.18693292
        ],
        [
            0.96163845, 0.76473117, 0.74806261, 0.60980642, 0.9281404,
            0.47227204, 0.89254606, 0.20130682
        ],
        [0., 0., 0., 0., 0., 0., 0., 0.],
        [0., 0., 0., 0., 0., 0., 0., 0.],
        [0., 0., 0., 0., 0., 0., 0., 0.],
        [0., 0., 0., 0., 0., 0., 0., 0.],
    ]
    hyps_expected = [[1, 0, 0, 3, 4, 1, 3, 4], [1, 4, 4, 1, 1, 3, 1, 0],
                     [0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0],
                     [0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0]]
    prev_hyps_expected = [[0, 1, 0, 1, 0, 1, 0, 1], [0, 1, 0, 1, 4, 1, 2, 1],
                          [0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0],
                          [0, 0, 0, 0, 0, 0, 0, 0], [0, 0, 0, 0, 0, 0, 0, 0]]

    hyp_str_expected = """
    beam_id: 1
    ids: 1
    ids: 2
    scores: 0.25818801
    scores: 0.65319967
    atten_vecs {
      prob: 0.38612545
      prob: 0.42067075
      prob: 0.84442794
    }
    atten_vecs {
      prob: 0.45298624
      prob: 0.53518069
      prob: 0.57700801
    }
    """
    atten_probs_expected = [
        [
            [0.45372832, 0.86230338, 0.65504861],
            [0.38612545, 0.42067075, 0.84442794],
            [0.45372832, 0.86230338, 0.65504861],
            [0.38612545, 0.42067075, 0.84442794],
            [0.45372832, 0.86230338, 0.65504861],
            [0.38612545, 0.42067075, 0.84442794],
            [0.45372832, 0.86230338, 0.65504861],
            [0.38612545, 0.42067075, 0.84442794],
        ],
        [
            [0.45372832, 0.86230338, 0.65504861],
            [0.38612545, 0.42067075, 0.84442794],
            [0.45372832, 0.86230338, 0.65504861],
            [0.38612545, 0.42067075, 0.84442794],
            [0.0532794, 0.53777719, 0.07609642],
            [0.38612545, 0.42067075, 0.84442794],
            [0.25818801, 0.03645897, 0.38127339],
            [0.38612545, 0.42067075, 0.84442794],
        ],
        [[0., 0., 0.], [0., 0., 0.], [0., 0., 0.], [0., 0., 0.], [0., 0., 0.],
         [0., 0., 0.], [0., 0., 0.], [0., 0., 0.]],
        [[0., 0., 0.], [0., 0., 0.], [0., 0., 0.], [0., 0., 0.], [0., 0., 0.],
         [0., 0., 0.], [0., 0., 0.], [0., 0., 0.]],
        [[0., 0., 0.], [0., 0., 0.], [0., 0., 0.], [0., 0., 0.], [0., 0., 0.],
         [0., 0., 0.], [0., 0., 0.], [0., 0., 0.]],
        [[0., 0., 0.], [0., 0., 0.], [0., 0., 0.], [0., 0., 0.], [0., 0., 0.],
         [0., 0., 0.], [0., 0., 0.], [0., 0., 0.]],
    ]

    scores = [
        tf.random.uniform([hyp_size, num_classes], seed=12345),
        tf.random.uniform([hyp_size, num_classes], seed=12346),
    ]
    init_atten_probs = tf.random.uniform([hyp_size, 3], seed=12345)
    atten_probs = tf.zeros([seq_len, hyp_size, 3])
    done_hyps = self._testBeamSearchOpHelper(
        hyp_size,
        num_beams,
        seq_len,
        0.,
        scores,
        init_atten_probs,
        atten_probs,
        best_scores_expected,
        cum_scores_expected,
        scores_expected,
        hyps_expected,
        prev_hyps_expected,
        atten_probs_expected,
        use_v2=use_v2)

    self._SameHyp(hyp_str_expected, done_hyps[1, 5])

  # The following 3 tests, test each step of this decoding tree.
  # Test that beam search finds the most probable sequence.
  # These probabilities represent the following search
  #
  #               G0 (0)
  #                  / \
  #                /     \
  #              /         \
  #            /             \
  #         0(0.6)          1(0.4)
  #           / \            / \
  #          /   \          /   \
  #         /     \        /     \
  #     0(0.55) 1(0.45) 0(0.05) 1(0.95)
  #
  # and these decoding probabilities
  # 000 - 0.6 * 0.55 = 0.33
  # 001 - 0.6 * 0.45 = 0.27
  # 010 - 0.4 * 0.05 = 0.02
  # 011 - 0.4 * 0.95 = 0.38
  #
  # Greedy would decode 000 since the first 0 is the most probable, but beam
  # should decode 011 since it's the highest probability then followed by 000.
  @parameterized.parameters(False, True)
  def _test_single_step_small_vocab_3(self, use_v2):
    hyp_size = 2
    num_beams = 1
    seq_len = 3

    probs = [np.log([[0.6, 0.4, 0.0000001], [0.6, 0.4, 0.0000001]])]
    done_hyps = self._testBeamSearchOpHelper(
        hyp_size,
        num_beams,
        seq_len,
        _MIN_SCORE,
        probs,
        init_atten_probs=tf.zeros([hyp_size, 0]),
        atten_probs=np.zeros([seq_len, hyp_size, 0]),
        best_scores_expected=[_MIN_SCORE],
        cum_scores_expected=np.log([0.6, 0.4]),
        scores_expected=[np.log([0.6, 0.4]), [0, 0], [0, 0]],
        hyps_expected=[[0, 1], [0, 0], [0, 0]],
        prev_hyps_expected=[[0, 0], [0, 0], [0, 0]],
        atten_probs_expected=np.zeros([seq_len, hyp_size, 0]),
        use_v2=use_v2)

    np.testing.assert_array_equal([['0', '0'], ['0', '0'], ['0', '0']],
                                  done_hyps)

  @parameterized.parameters(False, True)
  def test_two_steps_small_vocab_3(self, use_v2):
    hyp_size = 2
    num_beams = 1
    seq_len = 3

    probs = [
        np.log([[0.6, 0.4, 0.0000001], [0.6, 0.4, 0.0000001]]),
        np.log([[0.55, 0.45, 0.0000001], [0.05, 0.95, 0.0000001]]),
    ]
    done_hyps = self._testBeamSearchOpHelper(
        hyp_size,
        num_beams,
        seq_len,
        _MIN_SCORE,
        probs,
        init_atten_probs=tf.zeros([hyp_size, 0]),
        atten_probs=np.zeros([seq_len, hyp_size, 0]),
        best_scores_expected=[_MIN_SCORE],
        # Note, probabilites are swapped due to beams being swapped.
        cum_scores_expected=np.log([0.4 * 0.95, 0.6 * 0.55]),
        scores_expected=[np.log([0.6, 0.4]),
                         np.log([0.95, 0.55]), [0, 0]],
        hyps_expected=[[0, 1], [1, 0], [0, 0]],
        prev_hyps_expected=[[0, 0], [1, 0], [0, 0]],
        atten_probs_expected=np.zeros([seq_len, hyp_size, 0]),
        use_v2=use_v2)

    np.testing.assert_array_equal([[b'', b''], [b'', b''], [b'', b'']],
                                  done_hyps)

  @parameterized.parameters(False, True)
  def test_three_steps_eos(self, use_v2):
    hyp_size = 2
    num_beams = 1
    seq_len = 3

    probs = [
        np.log([[0.6, 0.4, 0.0000001], [0.6, 0.4, 0.0000001]]),
        np.log([[0.55, 0.45, 0.0000001], [0.05, 0.95, 0.0000001]]),
        # Finish the beams with EOS
        np.log([[0.05, 0.05, 0.9], [0.05, 0.05, 0.9]]),
    ]

    done_hyps = self._testBeamSearchOpHelper(
        hyp_size,
        num_beams,
        seq_len,
        _MIN_SCORE,
        probs,
        init_atten_probs=tf.zeros([hyp_size, 0]),
        atten_probs=np.zeros([seq_len, hyp_size, 0]),
        best_scores_expected=np.log([0.4 * 0.95 * 0.9]),
        cum_scores_expected=np.log([0.4 * 0.95 * 0.05, 0.4 * 0.95 * 0.05]),
        scores_expected=[
            np.log([0.6, 0.4]),
            np.log([0.95, 0.55]),
            np.log([0.05, 0.05])
        ],
        hyps_expected=[[0, 1], [1, 0], [0, 1]],
        prev_hyps_expected=[[0, 0], [1, 0], [0, 0]],
        atten_probs_expected=np.zeros([seq_len, hyp_size, 0]),
        use_v2=use_v2)

    expected_for_beam_0 = """
      beam_id: 0
      ids: 1
      ids: 1
      ids: 2
      scores: -0.916290700436  # = log 0.4
      scores: -0.0512933060527 # = log 0.95
      scores: -0.105360545218  # = log 0.9
      atten_vecs {
      }
      atten_vecs {
      }
      atten_vecs {
      }
      """

    expected_for_beam_1 = """
      beam_id: 0
      ids: 0
      ids: 0
      ids: 2
      scores: -0.510825574398  # = log 0.6
      scores: -0.597836971283  # = log 0.55
      scores: -0.105360545218  # = log 0.9
      atten_vecs {
      }
      atten_vecs {
      }
      atten_vecs {
      }
      """

    self._SameHyp(expected_for_beam_0, done_hyps[2, 0])
    self._SameHyp(expected_for_beam_1, done_hyps[2, 1])

  @parameterized.parameters(False, True)
  def test_three_steps_force_eos(self, use_v2):
    hyp_size = 2
    num_beams = 1
    seq_len = 3

    probs = [
        np.log([[0.6, 0.4, 0.0000001], [0.6, 0.4, 0.0000001]]),
        np.log([[0.55, 0.45, 0.0000001], [0.05, 0.95, 0.0000001]]),
        # EOS probability is still very low, so unless it is forced it will
        # not be in the beam.
        np.log([[0.45, 0.44, 0.01], [0.5, 0.5, 0.01]]),
    ]

    # Set expected values
    cum_scores_expected = np.log([0.4 * 0.95 * 0.45, 0.4 * 0.95 * 0.44])
    scores_expected = [
        np.log([0.6, 0.4]),
        np.log([0.95, 0.55]),
        np.log([0.45, 0.44])
    ]
    hyps_expected = [[0, 1], [1, 0], [0, 1]]
    prev_hyps_expected = [[0, 0], [1, 0], [0, 0]]

    # If force EOS is false, the we get empty hyps after beam search.
    done_hyps = self._testBeamSearchOpHelper(
        hyp_size,
        num_beams,
        seq_len,
        _MIN_SCORE,
        probs,
        init_atten_probs=tf.zeros([hyp_size, 0]),
        atten_probs=np.zeros([seq_len, hyp_size, 0]),
        best_scores_expected=[_MIN_SCORE],
        cum_scores_expected=cum_scores_expected,
        scores_expected=scores_expected,
        hyps_expected=hyps_expected,
        prev_hyps_expected=prev_hyps_expected,
        atten_probs_expected=np.zeros([seq_len, hyp_size, 0]),
        force_eos_in_last_step=False)
    np.testing.assert_array_equal([[b'', b''], [b'', b''], [b'', b'']],
                                  done_hyps)

    # If force eos is true, we get valid results as in test_three_step_eos,
    # but with lower probabilities (because of lower eos probs).
    done_hyps = self._testBeamSearchOpHelper(
        hyp_size,
        num_beams,
        seq_len,
        _MIN_SCORE,
        probs,
        init_atten_probs=tf.zeros([hyp_size, 0]),
        atten_probs=np.zeros([seq_len, hyp_size, 0]),
        best_scores_expected=np.log([0.4 * 0.95 * 0.01]),
        cum_scores_expected=cum_scores_expected,
        scores_expected=scores_expected,
        hyps_expected=hyps_expected,
        prev_hyps_expected=prev_hyps_expected,
        atten_probs_expected=np.zeros([seq_len, hyp_size, 0]),
        force_eos_in_last_step=True,
        use_v2=use_v2)

    expected_for_beam_0 = """
      beam_id: 0
      ids: 1
      ids: 1
      ids: 2
      scores: -0.916290700436  # = log 0.4
      scores: -0.0512933060527 # = log 0.95
      scores: -4.605170185988  # = log 0.01
      atten_vecs {
      }
      atten_vecs {
      }
      atten_vecs {
      }
      """

    expected_for_beam_1 = """
      beam_id: 0
      ids: 0
      ids: 0
      ids: 2
      scores: -0.510825574398  # = log 0.6
      scores: -0.597836971283  # = log 0.55
      scores: -4.605170185988  # = log 0.01
      atten_vecs {
      }
      atten_vecs {
      }
      atten_vecs {
      }
      """

    self._SameHyp(expected_for_beam_0, done_hyps[2, 0])
    self._SameHyp(expected_for_beam_1, done_hyps[2, 1])

  def testBeamSearchOpV2SmokeTest(self):
    hyp_size = 2
    num_beams = 1
    seq_len = 3
    probs = [
        np.log([[0.6, 0.4, 0.0000001], [0.6, 0.4, 0.0000001]]),
    ]
    results = self._runBeamSearchOpHelper(
        hyp_size,
        num_beams,
        seq_len,
        _MIN_SCORE,
        probs,
        init_atten_probs=tf.zeros([hyp_size, 0]),
        atten_probs=np.zeros([seq_len, hyp_size, 0]))
    expected_beam_done = np.array([False])
    self.assertAllEqual(results[-1], expected_beam_done)

  @parameterized.parameters(False, True)
  def testBeamSearchOpV2ThreeSteps(self, independence):
    """Similar setup as test_three_steps_eos above but for op V2."""
    hyp_size = 2
    num_beams = 1
    seq_len = 4
    small_prob = 1e-7
    probs = [
        np.log([[0.6, 0.4, small_prob], [0.6, 0.4, small_prob]]),
        np.log([[0.55, 0.45, small_prob], [0.05, 0.95, small_prob]]),
        # We insert id=1 here to make the decoded output with length 4.
        np.log([[small_prob, 1.0, small_prob], [small_prob, 1.0, small_prob]]),
        np.log([[0.05, 0.05, 0.9], [0.05, 0.05, 0.9]]),
    ]
    results = self._runBeamSearchOpHelper(
        hyp_size,
        num_beams,
        seq_len,
        _MIN_SCORE,
        probs,
        independence=independence,
        init_atten_probs=tf.zeros([hyp_size, 0]),
        atten_probs=np.zeros([seq_len, hyp_size, 0]))
    done_hyps = results[-4]
    hyp = hyps_pb2.Hypothesis()
    hyp.ParseFromString(done_hyps[3, 0])
    self.assertAllEqual(0, hyp.beam_id)
    self.assertAllEqual([1, 1, 1, 2], hyp.ids)
    # [log(0.4), log(0.95), log(1), log(0.9)]
    self.assertAllClose([-0.91629070, -0.05129331, 0., -0.10536052], hyp.scores)
    hyp.ParseFromString(done_hyps[3, 1])
    self.assertAllEqual(0, hyp.beam_id)
    self.assertAllEqual([0, 0, 1, 2], hyp.ids)
    # [log(0.6), log(0.55), log(1), log(0.9)]
    self.assertAllClose([-0.51082557, -0.59783697, 0., -0.10536052], hyp.scores)

  @parameterized.parameters(False, True)
  def testBeamSearchOpV2Independence(self, independence):
    """Test for V2 op's beam independence mode.

    The setup is the following: we have two beams and hyp_per_beam=2.

    Beam 0 has the same probablity setup as test_three_steps_eos above,
    except that we add a step by inserting id=1 at t=2 so that it finishes
    decoding in 4 steps, to [1, 1, 1, 2] (best) and [0, 0, 1, 2] (second best).

    Beam 1 encounters a terminated hyp at t=1: [1, 2]. But it also contains
    longer terminated hyps at t=3: [1,1,1,2] and [0, 0, 1, 2].

    We verify that under beam independence mode, for beam 1 the longer
    terminated hyps are not present. We achieve this by setting beam_size to
    be very small for force beam_done to True for beam 1.

    Args:
      independence: whether beam independence mode is enabled.
    """
    hyp_size = 4
    num_beams = 2
    seq_len = 4

    small_prob = 1e-7
    probs = [
        np.log([[0.6, 0.4, small_prob], [0.2, 0.8, small_prob],
                [0.6, 0.4, small_prob], [0.2, 0.8, small_prob]]),
        np.log([[0.55, 0.45, small_prob], [small_prob, 0.3, 0.6],
                [0.05, 0.95, small_prob], [0.05, 0.9, 0.05]]),
        # We insert id=1 here to make the decoded output with length 4.
        np.log([[small_prob, 1.0, small_prob], [small_prob, 1.0, small_prob],
                [small_prob, 1.0, small_prob], [small_prob, 1.0, small_prob]]),
        np.log([[0.05, 0.05, 0.9], [0.05, 0.05, 0.9], [0.05, 0.05, 0.9],
                [0.05, 0.05, 0.9]]),
    ]
    results = self._runBeamSearchOpHelper(
        hyp_size,
        num_beams,
        seq_len,
        _MIN_SCORE,
        probs,
        init_atten_probs=tf.zeros([hyp_size, 0]),
        atten_probs=np.zeros([seq_len, hyp_size, 0]),
        beam_size=0.1,
        independence=independence)
    done_hyps = results[-4]
    self.assertAllEqual(done_hyps.shape, [4, 4])

    hyp = hyps_pb2.Hypothesis()
    hyp.ParseFromString(done_hyps[1, 1])
    self.assertAllEqual(1, hyp.beam_id)
    self.assertAllEqual([1, 2], hyp.ids)
    # [log(0.8), log(0.6)]
    self.assertAllClose([-0.223144, -0.510826], hyp.scores)

    if not independence:
      # For beam 1, we have 3 terminated hyps when not under beam independence
      # mode.
      hyp.ParseFromString(done_hyps[3, 1])
      self.assertAllEqual(1, hyp.beam_id)
      self.assertAllEqual([1, 1, 1, 2], hyp.ids)
      # [log(0.8), log(0.3), log(1), log(0.9)]
      self.assertAllClose([-0.22314355, -1.20397282, 0., -0.10536052],
                          hyp.scores)
      hyp.ParseFromString(done_hyps[3, 3])
      self.assertAllEqual([0, 1, 1, 2], hyp.ids)
      self.assertAllEqual(1, hyp.beam_id)
      # [log(0.2), log(0.9), log(1), log(0.9)]
      self.assertAllClose([-1.609438, -0.105361, 0., -0.105361], hyp.scores)
    else:
      # Under beam independence mode, no further terminated hyps are found.
      for step_t in [2, 3]:
        for hyp_idx in [1, 3]:
          hyp.ParseFromString(done_hyps[step_t, hyp_idx])
          self.assertEmpty(hyp.ids)

    # For beam 0, we have 2 terminated hyps, similar to in test_three_steps_eos.
    hyp.ParseFromString(done_hyps[3, 0])
    self.assertAllEqual(0, hyp.beam_id)
    self.assertAllEqual([1, 1, 1, 2], hyp.ids)
    # [log(0.4), log(0.95), log(1), log(0.9)]
    self.assertAllClose([-0.91629070, -0.05129331, 0., -0.10536052], hyp.scores)
    hyp.ParseFromString(done_hyps[3, 2])
    self.assertAllEqual(0, hyp.beam_id)
    self.assertAllEqual([0, 0, 1, 2], hyp.ids)
    # [log(0.6), log(0.55), log(1), log(0.9)]
    self.assertAllClose([-0.51082557, -0.59783697, 0., -0.10536052], hyp.scores)

    expected_beam_done = np.array([True, True])
    self.assertAllEqual(results[-1], expected_beam_done)
    for steps in range(1, 4):
      # We verify that beam_done[1] is True after 2 steps (but it has no affect
      # when indpendence=False).
      results_at_steps = self._runBeamSearchOpHelper(
          hyp_size,
          num_beams,
          seq_len,
          _MIN_SCORE,
          probs[:steps],
          init_atten_probs=tf.zeros([hyp_size, 0]),
          atten_probs=np.zeros([seq_len, hyp_size, 0]),
          beam_size=0.1,
          independence=False)
      expected_beam_done = np.array([False, steps >= 2])
      self.assertAllEqual(results_at_steps[-1], expected_beam_done)

  def _testBeamSearchStoppingHelper(self,
                                    beam_size,
                                    ensure_full_beam,
                                    local_eos_threshold=-100,
                                    use_v2=True):
    hyp_size = 2
    num_beams = 1
    seq_len = 3
    probs = [
        # Only finish one beam with EOS.
        np.log([[0.05, 0.05, 0.9], [0.05, 0.9, 0.05]]),
    ]

    results = self._runBeamSearchOpHelper(
        hyp_size,
        num_beams,
        seq_len,
        _MIN_SCORE,
        probs,
        init_atten_probs=tf.zeros([hyp_size, 0]),
        atten_probs=np.zeros([seq_len, hyp_size, 0]),
        beam_size=beam_size,
        ensure_full_beam=ensure_full_beam,
        local_eos_threshold=local_eos_threshold,
        use_v2=use_v2)
    all_done = results[7]
    if use_v2:
      self.assertAllEqual([all_done], results[8])
    return all_done

  @parameterized.parameters(False, True)
  def test_beam_size_large(self, use_v2):
    # With default beam size, we are not yet all done, because we still have an
    # active hyp within 3.0 of best done hyp.
    all_done = self._testBeamSearchStoppingHelper(3.0, False, use_v2=use_v2)
    self.assertEqual(False, all_done)

  @parameterized.parameters(False, True)
  def test_beam_size_small(self, use_v2):
    # With small beam size, we are all done, because the active hyp is not
    # within such a narrow margin of best done hyp.
    all_done = self._testBeamSearchStoppingHelper(0.1, False, use_v2=use_v2)
    self.assertEqual(True, all_done)

  @parameterized.parameters(False, True)
  def test_ensure_full_beam(self, use_v2):
    # With small beam size and ensure_full_beam, we are _not_ yet done,
    # because we require to have two done hyps before stopping, regardless of
    # beam size.
    all_done = self._testBeamSearchStoppingHelper(0.1, True, use_v2=use_v2)
    self.assertEqual(False, all_done)

  @parameterized.parameters(False, True)
  def test_small_eos_threshold(self, use_v2):
    # With a small eos_threshold, we are done because the active hyp produced,
    # </s>, independent of small beam size.
    all_done = self._testBeamSearchStoppingHelper(
        0.1, False, -100.0, use_v2=use_v2)
    self.assertTrue(all_done)

  @parameterized.parameters(False, True)
  def test_large_eos_threshold(self, use_v2):
    # With larger eos_threshold, we are _not_ yet done, because we do not hit
    # </s> criteria we we require to have two done hyps before stopping,
    # regardless of beam size.
    all_done = self._testBeamSearchStoppingHelper(
        0.1, False, 0.01, use_v2=use_v2)
    self.assertFalse(all_done)

  def _SameHyp(self, expected_hyp_str, real_serialized_hyp):
    hyp1 = hyps_pb2.Hypothesis()
    text_format.Parse(expected_hyp_str, hyp1)
    hyp2 = hyps_pb2.Hypothesis()
    hyp2.ParseFromString(real_serialized_hyp)

    self.assertEqual(hyp1.beam_id, hyp2.beam_id)
    self.assertEqual(hyp1.ids, hyp2.ids)
    self.assertNear(hyp1.normalized_score, hyp2.normalized_score, 1e-6)
    self.assertAllClose(hyp1.scores, hyp2.scores)
    self.assertEqual(len(hyp1.atten_vecs), len(hyp2.atten_vecs))
    for av1, av2 in zip(hyp1.atten_vecs, hyp2.atten_vecs):
      self.assertAllClose(av1.prob, av2.prob)

  def testTopKTerminatedHypsOp(self):
    with self.session(use_gpu=False):
      hyp_size = 8
      num_beams = 2
      num_hyps_per_beam = hyp_size / num_beams
      seq_len = 6
      scores = tf.random.uniform([hyp_size, 5], seed=12345)
      atten_probs = tf.random.uniform([hyp_size, 3], seed=12345)
      src_seq_lengths = [3, 3]
      best_scores = tf.zeros([num_beams])
      cumulative_scores = tf.zeros([hyp_size])
      in_scores = tf.zeros([seq_len, hyp_size])
      in_hyps = tf.zeros([seq_len, hyp_size], dtype=tf.int32)
      in_prev_hyps = tf.zeros([seq_len, hyp_size], dtype=tf.int32)
      in_done_hyps = tf.as_string(tf.zeros([seq_len, hyp_size], dtype=tf.int32))
      in_atten_probs = tf.zeros([seq_len, hyp_size, 3])
      beam_done = tf.zeros([num_beams], dtype=tf.bool)

      (out_best_scores_0, out_cumulative_scores_0, out_scores_0, out_hyps_0,
       out_prev_hyps_0, out_done_hyps_0, out_atten_probs_0, beam_done,
       _) = ops.beam_search_step_v2(
           scores,
           atten_probs,
           best_scores,
           cumulative_scores,
           in_scores,
           in_hyps,
           in_prev_hyps,
           in_done_hyps,
           in_atten_probs,
           beam_done, [],
           0,
           eos_id=2,
           beam_size=3.0,
           num_hyps_per_beam=num_hyps_per_beam)

      outputs = ops.beam_search_step_v2(
          scores,
          atten_probs,
          out_best_scores_0,
          out_cumulative_scores_0,
          out_scores_0,
          out_hyps_0,
          out_prev_hyps_0,
          out_done_hyps_0,
          out_atten_probs_0,
          beam_done, [],
          1,
          eos_id=2,
          beam_size=3.0,
          num_hyps_per_beam=num_hyps_per_beam)

      # Get the topk terminated hyps.
      in_done_hyps = outputs[5]
      topk_hyps = ops.top_k_terminated_hyps(
          in_done_hyps,
          src_seq_lengths,
          k=2,
          num_hyps_per_beam=num_hyps_per_beam,
          length_normalization=0.2,
          coverage_penalty=0.2,
          target_seq_length_ratio=1.0)
      seq_ids, seq_lens, seq_scores = ops.unpack_hyp(
          tf.reshape(topk_hyps, [-1]), max_seq_length=5)

      k1, k2, k3, k4 = self.evaluate([topk_hyps, seq_ids, seq_lens, seq_scores])
      self.assertEqual(k1.size, 4)

      expected_top1_for_beam_0 = """
      beam_id: 0
      ids: 1
      ids: 2
      scores: 0.86230338
      scores: 0.65504861
      atten_vecs {
        prob: 0.45372832
        prob: 0.86230338
        prob: 0.65504861
      }
      atten_vecs {
        prob: 0.45372832
        prob: 0.86230338
        prob: 0.65504861
      }
      normalized_score: 1.002714
      """
      expected_top2_for_beam_1 = """
      beam_id: 1
      ids: 3
      ids: 2
      scores: 0.38127339
      scores: 0.57700801
      atten_vecs {
        prob: 0.38612545
        prob: 0.42067075
        prob: 0.84442794
      }
      atten_vecs {
        prob: 0.18693292
        prob: 0.17821217
        prob: 0.66380036
      }
      normalized_score: 0.480028
      """
      self._SameHyp(expected_top1_for_beam_0, k1[0, 0])
      self._SameHyp(expected_top2_for_beam_1, k1[1, 1])

      self.assertAllClose(
          k2,
          [[1, 2, 0, 0, 0], [4, 2, 0, 0, 0], [4, 2, 0, 0, 0], [3, 2, 0, 0, 0]])
      self.assertAllClose(k3, [2, 2, 2, 2])
      self.assertAllClose(k4, [1.002714, 0.684296, 0.522484, 0.480028])


if __name__ == '__main__':
  tf.test.main()
