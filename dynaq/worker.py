import random
from collections import deque
from multiprocessing import Process

import numpy as np
import torch
import torch.nn.functional as F
import torch.optim as optim
from matplotlib.pyplot import plot

from parallel_dqn.model import QNetwork
from parallel_dqn.replay_buffer import ReplayBuffer
import torch.multiprocessing as mp

from parallel_dqn.utils import copy_parameters

device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")


BUFFER_SIZE = int(1e5)  # replay buffer size
BATCH_SIZE = 64  # minibatch size

N = 10

class DynaQWorker(mp.Process):

    def __init__(self, id, env, ps, state_size, action_size, n_episodes, lr, gamma, update_every, max_t=1000, eps_start=1.0, eps_end=0.01, eps_decay=0.995):
        super(DynaQWorker, self).__init__()
        self.id = id
        self.ps = ps
        self.env = env
        self.state_size = state_size
        self.action_size = action_size
        self.n_episodes = n_episodes
        self.gamma = gamma
        self.update_every = update_every

        # TODO: It would probably be better if this was shared between all processes
        # However, that might hurt performance
        # Could instead maybe create one global memory and send a few experiences in batches?
        self.memory = ReplayBuffer(self.action_size, BUFFER_SIZE, BATCH_SIZE)

        self.qnetwork_local = QNetwork(state_size, action_size).to(device)
        self.qnetwork_target = QNetwork(state_size, action_size).to(device)

        self.optimizer = optim.SGD(self.qnetwork_local.parameters(), lr=lr)

        self.t_step = 0
        self.max_t = max_t
        self.eps_start = eps_start
        self.eps_end = eps_end
        self.eps_decay = eps_decay


    def act(self, state, eps=0.):
        """Returns actions for given state as per current policy.

        Params
        ======
            state (array_like): current state
            eps (float): epsilon, for epsilon-greedy action selection
        """

        # Epsilon-greedy action selection
        if random.random() > eps:
            # Turn the state into a tensor
            state = torch.from_numpy(state).float().unsqueeze(0).to(device)

            with torch.no_grad():
                action_values = self.qnetwork_local(state)  # Make choice based on local network

            return np.argmax(action_values.cpu().data.numpy())
        else:
            return random.choice(np.arange(self.action_size))

    def step(self, state, action, reward, next_state, done):
        # Save experience in replay memory
        self.memory.add(state, action, reward, next_state, done)

        # Update local parameters with that of parameter server
        copy_parameters(self.ps.get_parameters(), self.qnetwork_local.parameters())

        # Increment local timer
        self.t_step += 1

        # If enough samples are available in memory, get random subset and learn
        if len(self.memory) > BATCH_SIZE:
            experiences = self.memory.sample(BATCH_SIZE)
            self.learn(experiences)

            self.imagine_alternatives(N)


    def learn(self, experiences):
        """Update value parameters using given batch of experience tuples.
        Params
        ======
            experiences (Tuple[torch.Tensor]): tuple of (s, a, r, s', done) tuples
            gamma (float): discount factor
        """
        states, actions, rewards, next_states, dones = experiences

        # Get max predicted Q values (for next states) from target model
        Q_targets_next = self.qnetwork_target(next_states).detach().max(1)[0].unsqueeze(1)

        # Compute Q targets for current states
        Q_targets = rewards + (self.gamma * Q_targets_next * (1 - dones))

        # Get expected Q values from local model
        Q_expected = self.qnetwork_local(states).gather(1, actions)

        # Compute loss
        loss = F.mse_loss(Q_expected, Q_targets)
        # Minimize the loss
        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

        self.ps.record_gradients(self.id, self.qnetwork_local.get_gradients())

        # Learn every UPDATE_EVERY time steps.
        if self.t_step % self.update_every == 0:
            copy_parameters(self.ps.get_parameters(), self.qnetwork_target.parameters())


    def imagine_alternatives(self):
        experiences = self.memory.sample(N)
        states, actions, rewards, next_states, dones = experiences

       # rewards, next_states =


    def run(self):
        scores = []
        scores_window = deque(maxlen=100)  # last 100 scores
        eps = self.eps_start  # initialize epsilon
        for i_episode in range(1, self.n_episodes + 1):
            state = self.env.reset()
            score = 0
            for t in range(self.max_t):
                action = self.act(state, eps)
                # if do_render:
                #     self.env.render()
                next_state, reward, done, _ = self.env.step(action)
                self.step(state, action, reward, next_state, done)
                state = next_state
                score += reward
                if done:
                    break
            scores_window.append(score)  # save most recent score
            scores.append(score)  # save most recent score
            eps = max(self.eps_end, self.eps_decay * eps)  # decrease epsilon
            if self.id == 0:
                print('\rThread: {}, Episode {}\tAverage Score: {:.2f}'.format(self.id, i_episode, np.mean(scores_window)))
            if i_episode % 100 == 0:
                print('\rThread: {}, Episode {}\tAverage Score: {:.2f}'.format(self.id, i_episode, np.mean(scores_window)))
            if np.mean(scores_window) >= 200.0:
                print('\nEnvironment solved in {:d} episodes!\tAverage Score: {:.2f}'.format(i_episode - 100,
                                                                                             np.mean(scores_window)))
                torch.save(self.qnetwork_local.state_dict(), 'checkpoint.pth')
                break

        plot(id, scores)