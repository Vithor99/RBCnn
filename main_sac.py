import numpy as np
import torch
import matplotlib.pyplot as plt
import pickle
from simulation import Model
from rl_algos.actor_critic import ActorCritic
from rl_algos.soft_actor_critic import SoftActorCritic
from tqdm import tqdm
from torch.utils.tensorboard import SummaryWriter
import argparse
from steady import steady

import gymnasium as gym
from gymnasium.envs.registration import register
from gymnasium.vector import SyncVectorEnv

ss = steady()
parser = argparse.ArgumentParser()
parser.add_argument('--seed', default=0, type=int)
''' ARCHITECTURE '''
parser.add_argument('--n_layers', default=1, type=int)
parser.add_argument('--n_neurons', default=128, type=int)
''' ALGORITHM '''
parser.add_argument('--policy_var', default=-3.0, type=float)
parser.add_argument('--epsilon_greedy', default=0.0, type=float)
parser.add_argument('--gamma', default=ss.beta, type=float)
parser.add_argument('--lr', default=1e-3, type=float)
parser.add_argument('--batch_size', default=256, type=int)
parser.add_argument('--learn_std', default=0, type=int)
parser.add_argument('--use_hard_bounds', default=1, type=int)
''' SIMULATOR '''
parser.add_argument('--n_workers', default=8, type=int)
args = parser.parse_args()
seed = args.seed
np.random.seed(seed)
torch.manual_seed(seed)
torch.random.manual_seed(seed)
torch.cuda.manual_seed(seed)

# device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
device = torch.device('cpu')

name_exp = ''
for k, v in args.__dict__.items():
    name_exp += str(k) + "=" + str(v) + "_"

writer = SummaryWriter("logs/" + name_exp + "_random_sac5")

''' Define Simulator'''
c_ss, n_ss, k_ss, y_ss, u_ss, v_ss = ss.ss_adj()
state_dim = ss.states
action_dim = ss.actions
alpha = ss.alpha

action_bounds = {
    'order': [1, 0],
    ''
    'min': [lambda: 0,
            lambda: 0],
    'max': [lambda s0, s1, alpha, a1: torch.exp(s0) * (s1 ** alpha * a1 ** (1 - alpha)),
            lambda s0, s1, alpha, a1: 1.0]
}

''' Define Model'''
architecture_params = {'n_layers': args.n_layers,
                       'n_neurons': args.n_neurons,
                       'policy_var': args.policy_var,
                       'action_bounds': action_bounds,
                       'use_hard_bounds': args.use_hard_bounds
                       }

agent = SoftActorCritic(input_dim=state_dim,
                        architecture_params=architecture_params,
                        output_dim=action_dim,
                        lr=args.lr,
                        gamma=args.gamma,
                        epsilon=args.epsilon_greedy,
                        batch_size=args.batch_size,
                        alpha=alpha,
                        learn_std=args.learn_std == 1,
                        device=device).to(device)

register(
    id="model",
    entry_point="simulation:Model",
    kwargs={'k': k_ss,
            'var_k': 0.5 * k_ss,
            'gamma': ss.gamma,
            'psi': ss.psi,
            'delta': ss.delta,
            'rhoa': ss.rhoa,
            'alpha': ss.alpha,
            'T': 1000,
            'noise': 0.001},
)


def make_env():
    return gym.make("model")


test_sim = gym.make("model")

# random_util = ss.get_random_policy_utility(test_sim)

sims = SyncVectorEnv([make_env for _ in range(args.n_workers)])
# sims = gym.make_vec("model", num_envs=args.n_workers, vectorization_mode="async")
# sims = gym.make_vec("model", num_envs=args.n_workers, vectorization_mode="sync")

'''
Start Training the model 
'''
T = 1000
EPOCHS = 40000
frq_train = 3
frq_test = 100
n_eval = 1  # 0
best_utility = -np.inf

for iter in tqdm(range(EPOCHS)):

    st, _ = sims.reset()
    total_utility = 0

    for t in range(10):
        st_tensor = torch.from_numpy(st).float().to(device)
        with torch.no_grad():
            action_tensor, log_prob = agent.get_action(st_tensor)
            a = action_tensor.numpy()
            st1, u, done, _, y = sims.step(a)

            y = y['y']
            for i in range(args.n_workers):
                # agent.replay_buffer.push(st, a, u, st1, y)
                # agent.batchdata.push(st[i], a[i], log_prob[i].detach().cpu().numpy(), u[i], st1[i], y[i], float(not done[i]))
                agent.replay_buffer.add(st[i], a[i], log_prob[i].detach().cpu().numpy(), u[i], st1[i], y[i], done[i])

            st = st1
            total_utility += np.mean((agent.gamma ** t) * u)

    writer.add_scalar("train utility", total_utility, iter)  # v_ss-total_utility

    # qua alleniamo NN
    if iter % frq_train == (frq_train - 1):
        v_loss, p_loss, alpha_loss = agent.update()

        if v_loss is not None:
            writer.add_scalar("value loss", v_loss, iter)
            writer.add_scalar("policy loss", p_loss, iter)
            writer.add_scalar("alpha loss", alpha_loss, iter)

    '''
    Start Testing the model 
    '''
    if iter % frq_test == (frq_test - 1):

        '''qua sto testando la policy media'''

        total_utility = 0
        euler_gap = 0
        labor_gap = 0
        random_util = 0
        last_action = 0

        for _ in range(n_eval):
            last_sim = {}
            all_actions = np.zeros((T, 2))

            st, _ = test_sim.reset()
            rnd_state0 = st[1]

            for t in range(T):
                st_tensor = torch.from_numpy(st).float().to(device)
                with torch.no_grad():
                    action_tensor, log_prob = agent.get_action(st_tensor, test=True)
                    a = action_tensor.squeeze().numpy()
                    st1, u, done, _, y = test_sim.step(a)
                    y = y['y']

                    last_sim[t] = {'st': st,
                                   'a': a,
                                   'u': u,
                                   'st1': st1,
                                   'y': y}
                    all_actions[t, :] = a
                    total_utility += (agent.gamma ** t) * u

                    # random policy
                    rnd_util, rnd_state1 = ss.get_random_util(st[0], rnd_state0)
                    random_util += (agent.gamma ** t) * rnd_util
                    rnd_state0 = rnd_state1

                    # distance from FOC
                    if t > 0:
                        k0 = last_sim[t - 1]['st'][1]
                        k1 = last_sim[t]['st'][1]
                        z0 = last_sim[t - 1]['st'][0]
                        E_z1 = (1 - ss.rhoa) + ss.rhoa * z0
                        c0 = all_actions[t - 1, 0]
                        c1 = all_actions[t, 0]
                        n0 = all_actions[t - 1, 1]
                        n1 = all_actions[t, 1]
                        euler_gap += (c1 / c0) - ss.beta * ((1 - ss.delta) + E_z1 * ss.alpha * ((k1) ** (ss.alpha - 1)) * ((n1) ** (1 - ss.alpha)))
                        labor_gap += (c0 / ss.gamma) * (ss.psi / (1 - n0)) - (z0 * (1 - ss.alpha) * ((k0 / n0) ** ss.alpha))

                    if t == T - 1:
                        last_action += a

                    st = st1

                    if done:
                        break
            # distance from random policy: same initial capital, same shocks.
            # random_util += ss.get_random_policy_utility(last_sim, T)

        total_utility /= n_eval
        euler_gap /= n_eval * T
        labor_gap /= n_eval * T
        random_util /= n_eval
        last_action /= n_eval

        # writer.add_scalar("opt utility dist", v_ss-total_utility, iter) # np.abs(total_utility-v_ss)
        writer.add_scalar("Euler gap", euler_gap, iter)
        writer.add_scalar("Labor gap", labor_gap, iter)
        writer.add_scalar("improvement over random policy", (total_utility / random_util), iter)
        writer.add_scalar("distance from steady state", np.abs(last_action[0] - c_ss), iter)
        writer.add_scalar("var action 0 per sim", np.var(all_actions[:, 0]), iter)
        writer.add_scalar("var action 1 per sim", np.var(all_actions[:, 1]), iter)

        # writer.add_scalar("distance of action 0 from ss", np.abs(all_actions[1, 0]-c_ss)+np.abs(all_actions[-1, 0]-c_ss), iter)
        # writer.add_scalar("distance of action 1 from ss", np.abs(all_actions[1, 1]-n_ss)+np.abs(all_actions[-1, 1]-n_ss), iter)

        if best_utility < total_utility:
            best_utility = total_utility

            with open("last_sim.pkl", "wb") as f:
                pickle.dump(last_sim, f)

            agent.save("modello_bello")

        # plt.plot(utilities_train)
        # plt.title('Train Utility')
        # plt.show()
        #
        # plt.plot(utilities_test)
        # plt.title('Test Utility')
        # plt.show()

# plt.plot(value_losses, label='Value Loss')
# plt.plot(policy_losses, label='Policy Loss')
# plt.xlabel("Training Iterations")
# plt.ylabel("Loss")
# plt.title("Actor-Critic Training Loss")
# plt.legend()
# plt.show()




