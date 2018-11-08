import copy
import glob
import os
import time
import operator
from functools import reduce

import gym
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.autograd import Variable

from arguments import get_args
from vec_env.dummy_vec_env import DummyVecEnv
from vec_env.subproc_vec_env import SubprocVecEnv
from envs import make_env
from model import CNNPolicy, MLPPolicy
from storage import RolloutStorage
from visualize import visdom_plot

args = get_args()

num_updates = int(args.num_frames) // args.num_steps // args.num_processes

torch.manual_seed(args.seed)
if args.cuda:
    torch.cuda.manual_seed(args.seed)

try:
    os.makedirs(args.log_dir)
except OSError:
    files = glob.glob(os.path.join(args.log_dir, '*.monitor.csv'))
    for f in files:
        os.remove(f)

def main():
    os.environ['OMP_NUM_THREADS'] = '1'

    if args.vis:
        from visdom import Visdom
        viz = Visdom()
        win = None

    envs = [make_env(args.env_name, args.seed, i, args.log_dir, args.start_container)
                for i in range(args.num_processes)]
    for i in range(args.num_processes):
        envs[i].max_steps = 1200

    if args.num_processes > 1:
        envs = SubprocVecEnv(envs)
    else:
        envs = DummyVecEnv(envs)

    obs_shape = envs.observation_space.shape
    obs_shape = (obs_shape[0] * args.num_stack, *obs_shape[1:])
    obs_numel = reduce(operator.mul, obs_shape, 1)

    if len(obs_shape) == 3 and obs_numel > 1024:
        actor_critic = CNNPolicy(obs_shape[0], envs.action_space, args.recurrent_policy)
    else:
        assert not args.recurrent_policy, \
            "Recurrent policy is not implemented for the MLP controller"
        actor_critic = MLPPolicy(obs_numel, envs.action_space)

    modelSize = 0
    for p in actor_critic.parameters():
        pSize = reduce(operator.mul, p.size(), 1)
        modelSize += pSize
    print(str(actor_critic))
    print('Total model size: %d' % modelSize)

    if envs.action_space.__class__.__name__ == "Discrete":
        action_shape = 1
    else:
        action_shape = envs.action_space.shape[0]

    if args.cuda:
        actor_critic.cuda()

    if args.algo == 'a2c':
        optimizer = optim.RMSprop(actor_critic.parameters(), args.lr, eps=args.eps, alpha=args.alpha)

    rollouts = RolloutStorage(args.num_steps, args.num_processes, obs_shape, envs.action_space, actor_critic.state_size)
    current_obs = torch.zeros(args.num_processes, *obs_shape)

    def update_current_obs(obs):
        shape_dim0 = envs.observation_space.shape[0]
        obs = torch.from_numpy(obs).float()
        if args.num_stack > 1:
            current_obs[:, :-shape_dim0] = current_obs[:, shape_dim0:]
        current_obs[:, -shape_dim0:] = obs

    obs = envs.reset()
    update_current_obs(obs)

    rollouts.observations[0].copy_(current_obs)

    # These variables are used to compute average rewards for all processes.
    total_episode_rewards_avg = []
    total_episode_lengths_avg = []
    total_value_loss = []
    total_action_loss = []
    total_entropy = []

    episode_rewards = torch.zeros([args.num_processes, 1])
    final_rewards = torch.zeros([args.num_processes, 1])
    episode_lengths = torch.zeros([args.num_processes, 1])
    final_lengths = torch.zeros([args.num_processes, 1])

    reward_avg = 0
    length_avg = 0

    if args.cuda:
        current_obs = current_obs.cuda()
        rollouts.cuda()

    start = time.time()
    for j in range(num_updates):
        #Running an episode
        for step in range(args.num_steps):
            # Sample actions
            value, action, action_log_prob, states = actor_critic.act(
                Variable(rollouts.observations[step]),
                Variable(rollouts.states[step]),
                Variable(rollouts.masks[step])
            )
            cpu_actions = action.data.squeeze(1).cpu().numpy()
            # Exploration epsilon greedy
            if np.random.random_sample() < 0.2:
                cpu_actions = [envs.action_space.sample() for _ in range(args.num_processes)]

            # Observation, reward and next obs
            obs, reward, done, info = envs.step(cpu_actions)

            # Maxime: clip the reward within [0,1] for more reliable training
            # This code deals poorly with large reward values
            #reward = np.clip(reward, a_min=0, a_max=None) / 400

            scaled_reward = np.clip(reward + 0.4, a_min = -3.0, a_max=None)            
            scaled_reward = torch.from_numpy(np.expand_dims(np.stack(scaled_reward), 1)).float()

            reward = np.clip(reward, a_min=-4.0, a_max=None) + 1.0
            reward = torch.from_numpy(np.expand_dims(np.stack(reward), 1)).float()
            episode_rewards += reward
            episode_lengths += 1

            # If done then clean the history of observations.
            masks = torch.FloatTensor([[0.0] if done_ else [1.0] for done_ in done])
            final_rewards *= masks
            final_lengths *= masks
            final_rewards += (1 - masks) * episode_rewards
            final_lengths += (1 - masks) * episode_lengths
            episode_rewards *= masks
            episode_lengths *= masks

            if args.cuda:
                masks = masks.cuda()

            if current_obs.dim() == 4:
                current_obs *= masks.unsqueeze(2).unsqueeze(2)
            else:
                current_obs *= masks

            update_current_obs(obs)
            rollouts.insert(step, current_obs, states.data, action.data, action_log_prob.data, value.data, scaled_reward, masks)

        next_value = actor_critic(
            Variable(rollouts.observations[-1]),
            Variable(rollouts.states[-1]),
            Variable(rollouts.masks[-1])
        )[0].data

        rollouts.compute_returns(next_value, args.use_gae, args.gamma, args.tau)

        #Performing Actor Critic Updates
        if args.algo in ['a2c']:
            values, action_log_probs, dist_entropy, states = actor_critic.evaluate_actions(Variable(rollouts.observations[:-1].view(-1, *obs_shape)),
                                                                                           Variable(rollouts.states[0].view(-1, actor_critic.state_size)),
                                                                                           Variable(rollouts.masks[:-1].view(-1, 1)),
                                                                                           Variable(rollouts.actions.view(-1, action_shape)))

            values = values.view(args.num_steps, args.num_processes, 1)
            action_log_probs = action_log_probs.view(args.num_steps, args.num_processes, 1)

            advantages = Variable(rollouts.returns[:-1]) - values
            value_loss = advantages.pow(2).mean()

            action_loss = -(Variable(advantages.data) * action_log_probs).mean()

            optimizer.zero_grad()
            (value_loss * args.value_loss_coef + action_loss - dist_entropy * args.entropy_coef).backward()

            if args.algo == 'a2c':
                nn.utils.clip_grad_norm(actor_critic.parameters(), args.max_grad_norm)

            optimizer.step()

        rollouts.after_update()

        #Saving the model
        if j % args.save_interval == 0 and args.save_dir != "":
            save_path = os.path.join(args.save_dir, args.algo)
            try:
                os.makedirs(save_path)
            except OSError:
                pass

            # A really ugly way to save a model to CPU
            save_model = actor_critic
            if args.cuda:
                save_model = copy.deepcopy(actor_critic).cpu()

            save_model = [save_model,
                            hasattr(envs, 'ob_rms') and envs.ob_rms or None]

            torch.save(save_model, os.path.join(save_path, args.env_name + "_" + args.name + ".pt"))
            np.save(os.path.join(save_path, args.env_name + "_" + args.name + ".npy"), np.asarray([total_episode_rewards_avg, total_episode_lengths_avg, total_value_loss, total_action_loss, total_entropy]))

        #Logging the model
        if j % args.log_interval == 0:
            reward_avg = 0.99 * reward_avg + 0.01 * final_rewards.mean()
            length_avg = 0.99 * length_avg + 0.01 * final_lengths.mean()
            total_episode_rewards_avg.append(reward_avg)
            total_episode_lengths_avg.append(length_avg)
            total_value_loss.append(value_loss.data[0])
            total_action_loss.append(action_loss.data[0])
            total_entropy.append(dist_entropy.data[0])
            end = time.time()
            total_num_steps = (j + 1) * args.num_processes * args.num_steps

            print(
                "Updates {}, num timesteps {}, FPS {}, running avg reward {:.3f}, running avg eplen {:2f}, entropy {:.5f}, value loss {:.5f}, policy loss {:.5f}".
                format(
                    j,
                    total_num_steps,
                    int(total_num_steps / (end - start)),
                    reward_avg,
                    length_avg,
                    dist_entropy.data[0],
                    value_loss.data[0],
                    action_loss.data[0]
                )
            )

        if args.vis and j % args.vis_interval == 0:
            try:
                # Sometimes monitor doesn't properly flush the outputs
                win = visdom_plot(viz, win, args.log_dir, args.env_name, args.algo)
            except IOError:
                pass

if __name__ == "__main__":
    main()
