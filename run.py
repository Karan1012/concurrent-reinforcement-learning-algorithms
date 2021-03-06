import argparse
import gym

from utils.rl_algorithm_factory import RLAlgorithmFactory

GAMMA = 0.99  # discount factor
LR = 5e-4  # learning rate

def main():
    parser = argparse.ArgumentParser(description='Process arguments')
    parser.add_argument('--agent', type=str, default="dqn", help='Agent to use - dqn, a3c, or dynaq')
    parser.add_argument('--num-threads', type=int, default=3, help='Number of threads to use')
    parser.add_argument('--num-episodes', type=int, default=10000, help='Number of episodes')
    parser.add_argument('--do-render', type=bool, default=False, help='Whether or not to render game')
    args = parser.parse_args()

    env = gym.make('LunarLander-v2')

    alg = RLAlgorithmFactory.get(args.agent, env, args.do_render, args.num_threads, GAMMA, LR, args.num_episodes)
    alg.train()

    env.close()


if __name__ == "__main__":
    main()





