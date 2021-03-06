import random
import time
from collections import deque

import numpy as np
import torch
import torch.multiprocessing as mp
import torch.nn.functional as F
from torch import optim
from torch.distributions import Categorical

from a3c.model import ActorCriticNetwork

class A3CAgent(mp.Process):

    def __init__(self, id, env, state_size, action_size, gamma, lr, global_network, global_optimizer,
                 global_episode, n_episodes, max_t=1000, eps_start=1.0, eps_end=0.01, eps_decay=0.995):
        super(A3CAgent, self).__init__()

        self.id = id

        self.env = env
        self.state_size = state_size
        self.action_size = action_size
        self.env.seed(id)
        self.obs_dim = env.observation_space.shape[0]
        self.action_dim = env.action_space.n

        self.gamma = gamma

        self.local_network = ActorCriticNetwork(self.state_size, self.action_size)

        self.global_network = global_network
        self.global_optimizer = global_optimizer #optim.Adam(self.global_network.parameters(), lr=1e-3) #, momentum=.5)


        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        self.global_episode = global_episode
        self.n_episodes = n_episodes

        self.t_step = 0
        self.max_t = max_t
        self.eps_start = eps_start
        self.eps_end = eps_end
        self.eps_decay = eps_decay

        # sync local networks with global
        self.sync_with_global()

    def act(self, state, eps):
        if random.random() > eps:

            state = torch.FloatTensor(state).to(self.device)

            with torch.no_grad():
                logits, _ = self.global_network.forward(state)

            return np.argmax(logits.cpu().data.numpy())
        else:
            return random.choice(np.arange(self.action_size))


    def compute_loss(self, trajectory):
        states = torch.FloatTensor([sars[0] for sars in trajectory]).to(self.device)
        actions = torch.LongTensor([sars[1] for sars in trajectory]).view(-1, 1).to(self.device)
        rewards = torch.FloatTensor([sars[2] for sars in trajectory]).to(self.device)
        next_states = torch.FloatTensor([sars[3] for sars in trajectory]).to(self.device)
        dones = torch.FloatTensor([sars[4] for sars in trajectory]).view(-1, 1).to(self.device)

        # compute discounted rewards
        discounted_rewards = [torch.sum(torch.FloatTensor([self.gamma ** i for i in range(rewards[j:].size(0))]) \
                                        * rewards[j:]) for j in
                              range(rewards.size(0))]  # sorry, not the most readable code.

        logits, values = self.local_network.forward(states)
        dists = F.softmax(logits, dim=1)
        probs = Categorical(dists)

        # compute value loss
        value_targets = rewards.view(-1, 1) + torch.FloatTensor(discounted_rewards).view(-1, 1).to(self.device)
        value_loss = F.mse_loss(values, value_targets.detach())

        # compute entropy bonus
        entropy = []
        for dist in dists:
            entropy.append(-torch.sum(dist.mean() * torch.log(dist)))
        entropy = torch.stack(entropy).sum()

        # compute policy loss
        advantage = value_targets - values
        policy_loss = -probs.log_prob(actions.view(actions.size(0))).view(-1, 1) * advantage.detach()
        policy_loss = policy_loss.mean()

        total_loss = policy_loss + value_loss - 0.001 * entropy
        return total_loss

    def update_global(self, trajectory):
        loss = self.compute_loss(trajectory)

        self.global_optimizer.zero_grad()
        loss.backward()
        # propagate local gradients to global parameters
        for local_params, global_params in zip(self.local_network.parameters(), self.global_network.parameters()):
            global_params._grad = local_params._grad

        self.global_optimizer.step()

    def sync_with_global(self):
        self.local_network.load_state_dict(self.global_network.state_dict())


    def run(self):
        t_step = 0
        scores = []
        scores_window = deque(maxlen=100)  # last 100 scores
        eps = self.eps_start  # initialize epsilon
        start_time = time.time()
        for i_episode in range(1, self.n_episodes + 1):
            self.sync_with_global()
            state = self.env.reset()
            trajectory = []
            score = 0
            t_step += 1
            for t in range(self.max_t):
                action = self.act(state, eps)
                next_state, reward, done, _ = self.env.step(action)

                trajectory.append([state, action, reward, next_state, done])
                state = next_state
                score += reward
                if done:
                    with self.global_episode.get_lock():
                        self.update_global(trajectory)
                    break
            scores_window.append(score)  # save most recent score
            scores.append(score)  # save most recent score
            eps = max(self.eps_end, self.eps_decay * eps)  # decrease epsilon
            elapsed_time = time.time() - start_time
            if self.id == 0:
                print('\rThread: {}, Episode {}\tAverage Score: {:.2f}, Runtime: '.format(self.id, i_episode, np.mean(
                    scores_window)) + time.strftime("%H:%M:%S", time.gmtime(elapsed_time)))
            if i_episode % 100 == 0:
                print('\rThread: {}, Episode {}\tAverage Score: {:.2f}, Runtime: '.format(self.id, i_episode, np.mean(
                    scores_window)) + time.strftime("%H:%M:%S", time.gmtime(elapsed_time)))
            if np.mean(scores_window) >= 200.0:
                print('\nEnvironment solved in {:d} episodes!\tAverage Score: {:.2f}'.format(i_episode - 100,
                                                                                             np.mean(scores_window)))
                break
