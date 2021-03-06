import argparse

import torch


def get_args():
    parser = argparse.ArgumentParser(description='RL')
    parser.add_argument('--algo', default='a2c',
                        help='algorithm to use: a2c | ppo | acktr')
    parser.add_argument('--name', default='noname',
                        help='name of the model to save')
    parser.add_argument('--lr', type=float, default=7e-4,
                        help='learning rate (default: 7e-4)')
    parser.add_argument('--eps', type=float, default=1e-5,
                        help='RMSprop optimizer epsilon (default: 1e-5)')
    parser.add_argument('--alpha', type=float, default=0.99,
                        help='RMSprop optimizer apha (default: 0.99)')
    parser.add_argument('--gamma', type=float, default=0.99,
                        help='discount factor for rewards (default: 0.99)')
    parser.add_argument('--use-gae', action='store_true', default=False,
                        help='use generalized advantage estimation')
    parser.add_argument('--tau', type=float, default=0.95,
                        help='gae parameter (default: 0.95)')
    parser.add_argument('--exp_probability', type=float, default=0.0,
                        help='probability for exploration (default: 0.0)')
    parser.add_argument('--entropy-coef', type=float, default=0.01,
                        help='entropy term coefficient (default: 0.01)')
    parser.add_argument('--value-loss-coef', type=float, default=1.0,
                        help='value loss coefficient (default: 0.5)')
    parser.add_argument('--max-grad-norm', type=float, default=0.5,
                        help='value loss coefficient (default: 0.5)')
    parser.add_argument('--seed', type=int, default=1,
                        help='random seed (default: 1)')
    parser.add_argument('--num-processes', type=int, default=1,
                        help='how many training CPU processes to use')
    parser.add_argument('--num-steps', type=int, default=40,
                        help='number of forward steps in A2C (default: 5)')
    parser.add_argument('--num-stack', type=int, default=1,
                        help='number of frames to stack')
    parser.add_argument('--log-interval', type=int, default=1,
                        help='log interval, one log per n updates (default: 10)')
    parser.add_argument('--save-interval', type=int, default=2000,
                        help='save interval, one save per n updates (default: 10)')
    parser.add_argument('--vis-interval', type=int, default=2000,
                        help='vis interval, one log per n updates (default: 100)')
    parser.add_argument('--num-frames', type=int, default=10e7,
                        help='number of frames to train')
    parser.add_argument('--env-name', default='PongNoFrameskip-v4',
                        help='environment to train on (default: PongNoFrameskip-v4)')
    parser.add_argument('--log-dir', default='/tmp/gym/',
                        help='directory to save agent logs (default: /tmp/gym)')
    parser.add_argument('--save-dir', default='./trained_models/',
                        help='directory to save agent logs (default: ./trained_models/)')
    parser.add_argument('--no-cuda', action='store_true', default=False,
                        help='disables CUDA training')
    parser.add_argument('--recurrent-policy', action='store_true', default=False,
                        help='use a recurrent policy')
    parser.add_argument('--discrete-actions', action='store_true', default=False,
                        help='use a discrete wrapper')    
    parser.add_argument('--num-recsteps', type=int, default=5,
                        help='number of recurrent steps in A2C (default: 5)')
    parser.add_argument('--continuous-var', type=float, default=0.01,
                        help='variance of the continuous action (default: 0.16)')
    parser.add_argument('--reward-pow', type=float, default=1.0,
                        help='power of reward (default: 1.0)')
    parser.add_argument('--reward-slack', type=float, default=0.4,
                        help='slack variable for reward (default: 0.4)')
    parser.add_argument('--reward-factor', type=float, default=0.0,
                        help='factor variable for reward (default: 0.0)')
    parser.add_argument('--reward-facpow', type=float, default=1.0,
                        help='factor variable for reward power (default: 1)')
    parser.add_argument('--no-vis', action='store_true', default=False,
                        help='disables visdom visualization')
    parser.add_argument('--start-container', action='store_true', default=False,
                        help='start the Duckietown container image')
    parser.add_argument('--use-mixed', action='store_true', default=False,
                        help='use mixed distribution')
    parser.add_argument('--use-batchnorm', action='store_true', default=False,
                        help='whether or not use batchnorm in the CNN policy')
    parser.add_argument('--use-residual', action='store_true', default=False,
                        help='whether or not use residual block in the CNN policy')
    parser.add_argument('--use-vae', action='store_true', default=False,
                        help='whether or not use VAE')


    args = parser.parse_args()

    args.cuda = not args.no_cuda and torch.cuda.is_available()
    args.vis = not args.no_vis

    return args
