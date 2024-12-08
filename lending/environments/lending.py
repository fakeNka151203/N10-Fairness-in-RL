# coding=utf-8
# Copyright 2022 The ML Fairness Gym Authors.
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

# Lint as: python2, python3
"""ML Fairness gym loan environment.
This environment is meant to be a hello-world example to the gym as well as
serve as a template for writing future environments.
In each step step, the agent decides whether to accept or reject an application.
Applicant features are generated by a mixture model which also determines the
likelihood of defaulting.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import copy
import enum
from typing import List, Optional

from absl import logging
import attr
from gym import spaces
import matplotlib
import matplotlib.pyplot as plt
import numpy as np


# Used for rending applicant features.
from lending.environments import lending_params, core, multinomial

_MARKERS = matplotlib.markers.MarkerStyle.filled_markers


class LoanDecision(enum.IntEnum):
  """Enum representing possible loan decisions."""
  REJECT = 0
  ACCEPT = 1


class _CashUpdater(core.StateUpdater):
  """Changes bank_cash as a result of an action."""

  def update(self, state, action):
    params = state.params
    if action == LoanDecision.REJECT:
      return
    if state.will_default:
      state.bank_cash -= params.loan_amount
    else:
      state.bank_cash += params.loan_amount * params.interest_rate


class _ApplicantSampler(core.StateUpdater):
  """Samples a new applicant."""

  def update(self, state, action):
    del action  # Unused.
    params = state.params
    new_applicant = params.applicant_distribution.sample(state.rng)
    state.applicant_features = np.clip(new_applicant.features,
                                       params.min_observation,
                                       params.max_observation)
    state.group = new_applicant.group
    state.group_id = np.argmax(new_applicant.group)
    state.will_default = new_applicant.will_default


@attr.s(cmp=False)  # Use core.State's equality methods.
class State(core.State):
  """State object for lending environments."""

  # Random number generator for the simulation.
  rng = attr.ib()  # type: np.random.RandomState

  # State parameters that can evolve over time.
  params = attr.ib()  # type: lending_params.Params

  # Number of loans available for the bank.
  bank_cash = attr.ib()  # type: float

  # Applicant-related attributes are Optional with defaults of None so that the
  # object can be initialized in two steps, first with applicant attributes as
  # None, then a StateUpdater is used to fill in the applicant features.
  applicant_features = attr.ib(default=None)  # type: Optional[np.ndarray]
  group = attr.ib(default=None)  # type: Optional[List[int]]
  group_id = attr.ib(default=None)  # type: Optional[int]
  will_default = attr.ib(default=None)  # type: Optional[bool]


class BaseLendingEnv(core.FairnessEnv):
  """Base loan decision environment.
  In each step, the agent decides whether to accept or reject an
  application.
  The base class is abstract.
  """

  metadata = {'render.modes': ['human']}
  default_param_builder = lending_params.Params
  group_membership_var = 'group'
  _cash_updater = _CashUpdater()
  _parameter_updater = core.NoUpdate()
  _applicant_updater = _ApplicantSampler()

  def __init__(self, params = None):
    params = (
        self.default_param_builder() if params is None else params
        )  # type: lending_params.Params

    # The action space of the agent is Accept/Reject.
    self.action_space = spaces.Discrete(2)

    # Bank's cash is a scalar and cannot be negative.
    bank_cash_space = spaces.Box(
        low=0, high=params.max_cash, shape=(), dtype=np.float64)

    # Two-dimensional observation space describes each loan applicant.
    loan_applicant_space = spaces.Box(
        params.min_observation,
        params.max_observation,
        dtype=np.float32,
        shape=(params.applicant_distribution.dim,))

    group_space = spaces.MultiBinary(params.num_groups)

    self.observable_state_vars = {
        'bank_cash': bank_cash_space,
        'applicant_features': loan_applicant_space,
        'group': group_space
    }

    super(BaseLendingEnv, self).__init__(params)
    self._state_init()

  def _state_init(self, rng=None):
    self.state = State(
        # Copy in case state.params get mutated, initial_params stays pristine.
        params=copy.deepcopy(self.initial_params),
        rng=rng or np.random.RandomState(),
        bank_cash=self.initial_params.bank_starting_cash)
    self._applicant_updater.update(self.state, None)

  def reset(self):
    """Resets the environment."""
    self._state_init(self.state.rng)
    return super(BaseLendingEnv, self).reset()

  def _is_done(self):
    """Returns True if the bank cash is less than loan_amount."""
    return self.state.bank_cash < self.state.params.loan_amount

  def _step_impl(self, state, action):
    """Run one timestep of the environment's dynamics.
    In a single step, the agent decides whether to accept or reject an
    application.
    The potential payoffs of rejected application are always 0.
    If an application is accepted, the payoffs are:
      -loan_amount if the applicant defaults.
      +loan_amount*interest_rate if the applicant successfully pays back.
    Args:
      state: A `State` object containing the current state.
      action: An action in `action_space`.
    Returns:
      A `State` object containing the updated state.
    """

    self._cash_updater.update(self.state, action)
    self._parameter_updater.update(self.state, action)
    self._applicant_updater.update(self.state, action)
    return self.state

  def render(self, mode='human'):
    """Renders the history and current state using matplotlib.
    Args:
      mode: string indicating the rendering mode. The only supported mode is
        `human`.
    """

    if mode == 'human':
      if self.state.params.applicant_distribution.dim != 2:
        raise NotImplementedError(
            'Cannot render if applicant features are not exactly 2 dimensional. '
            'Got %d dimensional applicant features.' %
            self.state.params.applicant_distribution.dim)

      plt.figure(figsize=(12, 4))
      plt.subplot(1, 2, 1)
      plt.xlim(-2, 2)
      plt.ylim(-2, 2)
      plt.title('Applicant Features')
      plt.xticks([], [])
      plt.yticks([], [])
      for state, action in self.history:
        if action == 1:
          x, y = state.applicant_features
          color = 'r' if state.will_default else 'b'
          plt.plot([x], [y], _MARKERS[state.group_id] + color, markersize=12)
      plt.xlabel('Feature 1')
      plt.ylabel('Feature 2')

      x, y = self.state.applicant_features

      plt.plot([x], [y], _MARKERS[self.state.group_id] + 'k', markersize=15)

      plt.subplot(1, 2, 2)
      plt.title('Cash')
      plt.plot([state.bank_cash for state, _ in self.history] +
               [self.state.bank_cash])
      plt.ylabel('# loans available')
      plt.xlabel('Time')
      plt.tight_layout()
    else:
      super(BaseLendingEnv, self).render(mode)  # Raises NotImplementedError


class SimpleLoans(BaseLendingEnv):
  """Simple lending environment.
  Applicants have 2D features which can be used to determine whether they have
  high or low likelihood of success.
  """
  default_param_builder = lending_params.Params


class DifferentialExpressionEnv(BaseLendingEnv):
  """Lending environment with groups that present creditworthiness differently.
  Applicants have 2D features which can be used to determine whether they have
  high or low likelihood of success, but the mapping is different for the
  different groups.
  """
  default_param_builder = lending_params.DifferentialExpressionParams


class _CreditShift(core.StateUpdater):
  """Updates the cluster probabilities based on the repayment."""

  def update(self, state, action):
    """Updates the cluster probabilities based on the repayment.
    Successful repayment raises one's credit score and default lowers one's
    credit score. This is expressed by moving a small amount of probability mass
    (representing an individual) from one credit-score cluster to an adjacent
    one.
    This change in credit only happens if the applicant is accepted. Rejected
    applicants experience no change in their score.
    state.params is mutated in place; nothing is returned.
    Args:
      state: A core.State object.
      action: a `LoanDecision`.
    """

    if action == LoanDecision.REJECT:
      return

    params = state.params
    group_id = state.group_id

    # Group should always be a one-hot encoding of group_id. This assert tests
    # that these two values have not somehow gotten out of sync.
    assert state.group_id == np.argmax(
        state.group), 'Group id %s. group %s' % (state.group_id,
                                                 np.argmax(state.group))

    # Cast to list so we can mutate it.
    cluster_probs = list(
        params.applicant_distribution.components[group_id].weights)

    rng = np.random.RandomState()
    for _ in range(10):
      group = params.applicant_distribution.components[group_id].sample(
          rng).group
      assert np.array_equal(group, state.group), (
          'Sampling from the component that is indexed here does not give '
          'members of the group that is intended to be affected. Something is '
          'quite wrong. Check that your group ids are in order in the credit '
          'cluster spec. sampled group_id %s vs state.group %s. '
          'Component[%d]: %s' %
          (group, state.group, group_id,
           params.applicant_distribution.components[group_id]))

    # Assert argmax gives the right index.
    for idx, component in enumerate(
        params.applicant_distribution.components[group_id].components):
      credit_score = component.sample(rng).features
      assert np.argmax(credit_score) == idx, '%s vs %s' % (credit_score, idx)

    # This applicant has their credit score lowered or raised.
    cluster_id = np.argmax(state.applicant_features)
    new_cluster = (cluster_id - 1 if state.will_default else cluster_id + 1)

    # Prevents falling off the edges of the cluster array.
    new_cluster = min(new_cluster, len(cluster_probs) - 1)
    new_cluster = max(new_cluster, 0)

    # Prevents moving more probability mass than this bucket has.
    assert cluster_probs[cluster_id] > 0, (
        'This cluster was sampled but has no mass. %d. Full distribution %s' %
        (cluster_id, cluster_probs))

    mass_to_shift = min(params.cluster_shift_increment,
                        cluster_probs[cluster_id])

    # Mutates params.cluster_probs[group_id].
    cluster_probs[cluster_id] -= mass_to_shift
    cluster_probs[new_cluster] += mass_to_shift
    logging.debug('Group %d: Moving mass %f from %d to %d', group_id,
                  mass_to_shift, cluster_id, new_cluster)

    assert np.abs(np.sum(cluster_probs) -
                  1) < 1e-6, 'Cluster probs must sum to 1.'
    assert all([prob >= 0 for prob in cluster_probs
               ]), 'Cluster probs must be non-negative'

    state.params.applicant_distribution.components[
        group_id].weights = cluster_probs


class DelayedImpactEnv(BaseLendingEnv):
  """Lending environment in which outcomes affect future credit.
  Each applicant has a credit score which causally determines their likelihood
  of success. Applicants who default have their credit lowered while applicants
  who pay back have their credit raised.
  Based on the environment described in Liu et al's Delayed Impact of Machine
  Learning: https://arxiv.org/abs/1803.04383
  """
  default_param_builder = lending_params.DelayedImpactParams
  _parameter_updater = _CreditShift()

  def __init__(self, params=None):
    super(DelayedImpactEnv, self).__init__(params)
    self.observable_state_vars['applicant_features'] = multinomial.Multinomial(
        self.initial_params.applicant_distribution.dim, 1)
    self.observation_space = spaces.Dict(self.observable_state_vars)