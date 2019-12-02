from parallel_dqn.parameter_server import ParameterServer
from parallel_dqn.replay_buffer import ReplayBuffer
from parallel_dqn.worker import ParallelDQNWorker
from utils.agent import Agent

UPDATE_EVERY = 5
BUFFER_SIZE = int(1e5)  # replay buffer size
BATCH_SIZE = 64  # minibatch size

class ParallelDQNAgent(Agent):
    def __init__(self, env, num_threads, gamma, lr, global_max_episode):


        self.ps = ParameterServer(env.observation_space.shape[0], env.action_space.n, 0, num_threads, UPDATE_EVERY, lr)
        # TODO: It would probably be better if this was shared between all processes
        # However, that might hurt performance
        # Could instead maybe create one global memory and send a few experiences in batches?
      #  self.memory = ReplayBuffer(env.action_space.n, BUFFER_SIZE, BATCH_SIZE)

        self.workers = [ParallelDQNWorker(id=id, env=env, ps=self.ps, state_size=env.observation_space.shape[0],
                      action_size=env.action_space.n, n_episodes=global_max_episode, lr=lr, gamma=gamma, update_every=UPDATE_EVERY) for id in range(num_threads)]

    def train(self):
       # self.ps.start()

        [worker.start() for worker in self.workers]
        [worker.join() for worker in self.workers]

