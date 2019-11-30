import torch
import torch.multiprocessing as mp

from a3c.model import ValueNetwork, PolicyNetwork
from a3c.utils import SharedAdam
from a3c.worker import A3CWorker
from utils.agent import Agent


class A3CAgent(Agent):

    def __init__(self, env, num_threads, gamma, lr, global_max_episode):
        self.env = env

        self.gamma = gamma
        self.lr = lr
        self.global_episode = mp.Value('i', 0)
        self.GLOBAL_MAX_EPISODE = global_max_episode

        self.global_value_network = ValueNetwork(self.env.observation_space.shape[0], 1)
        self.global_value_network.share_memory()
        self.global_policy_network = PolicyNetwork(self.env.observation_space.shape[0], self.env.action_space.n)
        self.global_policy_network.share_memory()
        self.global_value_optimizer = SharedAdam(self.global_value_network.parameters(), lr=lr)
        self.global_policy_optimizer = SharedAdam(self.global_policy_network.parameters(), lr=lr)
        self.global_value_optimizer.share_memory()
        self.global_policy_optimizer.share_memory()

        self.workers = [A3CWorker(i, env, self.gamma, self.global_value_network, self.global_policy_network, \
                                        self.global_value_optimizer, self.global_policy_optimizer, self.global_episode,
                                        self.GLOBAL_MAX_EPISODE) for i in range(num_threads)]

    def train(self):
        [worker.start() for worker in self.workers]
        [worker.join() for worker in self.workers]

    def save_model(self):
        torch.save(self.global_value_network.state_dict(), "a3c_value_model.pth")
        torch.save(self.global_policy_network.state_dict(), "a3c_policy_model.pth")