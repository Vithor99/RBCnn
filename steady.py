# This script computes the steady state of the model 
import numpy as np
from scipy.optimize import fsolve

class steady:
    def __init__(self):
        self.beta = 0.99
        self.gamma = 1 #consumption pref
        self.psi = 1.6
        self.delta = 0.025 #depreciation rate
        self.rhoa = 0.9 #AR coff 
        self.alpha = 0.35 #prduction function

        self.states = 2 
        self.actions = 2
    
    def equations(self, vars):
        c, n, k = vars

        #ls = (1-self.alpha)*(k**self.alpha)*(n**(-self.alpha)) - (self.psi/self.gamma)*(np.sqrt(c)/np.sqrt(1-n))
        ls = (1-self.alpha)*(k**self.alpha)*(n**(-self.alpha)) - (self.psi/self.gamma)*(c/(1-n))
        
        ee = 1 - self.beta*((1-self.delta)+self.alpha*k**(self.alpha-1)*n**(1-self.alpha))  
        kt = self.delta*k - k**self.alpha * n**(1-self.alpha) + c 
        return [ls, ee, kt]
    
    def ss(self):
        initial_guess = [0.5, 0.5, 0.5]
        solution = fsolve(self.equations, initial_guess)
        c_ss, n_ss, k_ss = solution
        y_ss = (k_ss)**self.alpha * (n_ss)**(1-self.alpha)

        #u_ss = self.gamma*np.sqrt(c_ss)+self.psi*np.sqrt(1-n_ss)
        u_ss = self.gamma*np.log(c_ss)+self.psi*np.log(1-n_ss)

        v_ss = 0
        for t in range(100):
            v_ss += (self.beta**t) * u_ss
        
        return c_ss, n_ss, k_ss, y_ss, u_ss, v_ss
    
        #include a function that computes the value with the number of periods as input 

    def ss_adj(self):
        c_ss, n_ss, k_ss, y_ss, u_ss, v_ss = self.ss()
        c_ss = c_ss
        n_ss = n_ss
        k_ss = k_ss
        y_ss = (k_ss)**self.alpha * (n_ss)**(1-self.alpha)
        u_ss = u_ss
        v_ss = 0
        for t in range(100):
            v_ss += self.beta**t * u_ss
        return c_ss, n_ss, k_ss, y_ss, u_ss, v_ss
    
    def foc_log(self, c, c1, n, n1, k, k1):
        ls = (1-self.alpha)*(k**self.alpha)*(n**(-self.alpha)) - (self.psi/self.gamma)*(c/(1-n))
        ee = (self.gamma/c) - self.beta*(self.gamma/c1)*((1-self.delta)+self.alpha*k1**(self.alpha-1)*n1**(1-self.alpha)) 
        return ls, ee
    
    def foc_sqrt(self, c, c1, n, n1, k, k1):
        ls = (1-self.alpha)*(k**self.alpha)*(n**(-self.alpha)) - (self.psi/self.gamma)*(np.sqrt(c)/np.sqrt(1-n))
        ee = (self.gamma/np.sqrt(c)) - self.beta*(self.gamma/np.sqrt(c1))*((1-self.delta)+self.alpha*k1**(self.alpha-1)*n1**(1-self.alpha)) 
        return ls, ee

    def get_random_policy_utility(self, last_sim, T): #we can eliminate? 
        upper_bound_1 = 1.0
        upper_bound_0 = lambda s0, s1, alpha, a1: s0 * (s1**alpha * a1**(1-alpha))

        #st, _ = sim.reset()
        st = np.array([1, last_sim[0]['st'][1]])
        z = [v['st1'][0] for v in last_sim.values()]
        random_util = 0

        for t in range(T):
            rnd_a_1 = np.random.uniform(0.0, upper_bound_1)
            rnd_a_0 = np.random.uniform(0.0, upper_bound_0(st[0], st[1], self.alpha, rnd_a_1))
            a = np.array([rnd_a_0, rnd_a_1])

            y = st[0]*(st[1]**self.alpha) * (rnd_a_1**(1-self.alpha))
            u = self.gamma*np.log(rnd_a_0)+self.psi*np.log(1-rnd_a_1)
            k1 =  (1-self.delta)*st[1] + y - rnd_a_0
            st = np.array([z[t], k1])
            #st, u, done, _, y = sim.step(a)
            random_util += (self.beta ** t) * u

        return random_util
    
    def get_random_util(self, z, k):
        upper_bound_1 = 1.0
        upper_bound_0 = lambda s0, s1, alpha, a1: s0 * (s1**alpha * a1**(1-alpha))

        rnd_a_1 = np.random.uniform(0.0, upper_bound_1)
        rnd_a_0 = np.random.uniform(0.0, upper_bound_0(z, k, self.alpha, rnd_a_1))
        y = z*(k**self.alpha) * (rnd_a_1**(1-self.alpha))

        U = self.gamma*np.log(rnd_a_0)+self.psi*np.log(1-rnd_a_1)
        k1 = (1-self.delta)*k + y - rnd_a_0
        return U, k1

    


ss = steady()
c_ss, n_ss, k_ss, y_ss, u_ss, v_ss = ss.ss_adj()