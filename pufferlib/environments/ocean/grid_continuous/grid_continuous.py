from pdb import set_trace as T
import numpy as np
import os

import pettingzoo
import gymnasium

import pufferlib
from pufferlib.environments.ocean.grid_continuous.c_grid_continuous import Environment as CEnv

EMPTY = 0
FOOD = 1
WALL = 2
AGENT_1 = 3
AGENT_2 = 4
AGENT_3 = 5
AGENT_4 = 6

PASS = 0
NORTH = 1
SOUTH = 2
EAST = 3
WEST = 4

COLORS = np.array([
    [6, 24, 24, 255],     # Background
    [0, 0, 255, 255],     # Food
    [0, 128, 255, 255],   # Corpse
    [128, 128, 128, 255], # Wall
    [255, 0, 0, 255],     # Snake
    [255, 255, 255, 255], # Snake
    [255, 85, 85, 255],     # Snake
    [170, 170, 170, 255], # Snake
], dtype=np.uint8)

def init_introverts(env):
    pass

def reward_introverts(env):
    '''-1 for each nearby agent'''
    raw_rewards = 1 - (env.obs_view>=AGENT_1).sum(axis=(1,2))
    return np.clip(raw_rewards/10, -1, 0)

def reward_centralized(env):
    '''Centralized Euclidean distance'''
    pos = env.agent_positions / env.map_size
    sq_diff = (pos[None, :, :] - pos[:, None, :])**2
    return np.sqrt(sq_diff.sum(2)).sum(1) / env.map_size

def init_introverts(env):
    pass

def init_foraging(env, food_prob=0.1):
    rng = np.random.rand(env.height, env.width)
    env.grid[(rng<food_prob) * (env.grid==EMPTY)] = FOOD
    env.grid[(rng>=food_prob) * (env.grid==EMPTY)] = EMPTY

def reward_foraging(env):
    return np.zeros(env.num_agents, dtype=np.float32)

def init_predator_prey(env):
    n = env.num_agents // 2
    env.agent_colors[:n] = AGENT_1
    env.agent_colors[n:] = AGENT_2

def reward_predator_prey(env):
    rewards = np.zeros(env.num_agents, dtype=np.float32)
    n = env.num_agents // 2

    # Predator wants to keep prey in sight
    rewards[:n] = (env.obs_view[:n] == AGENT_2).sum(axis=(1,2))

    # Prey wants to keep predator out of sight
    rewards[n:] = -(env.obs_view[n:] == AGENT_1).sum(axis=(1,2))

    return np.clip(rewards/10, -1, 1)

def init_group(env):
    pass

def reward_group(env):
    same_group = env.obs_view == env.agent_colors[:, None, None]
    same_reward = same_group.sum(axis=(1,2)) - 1
    diff_group = (env.obs_view>=AGENT_1) * (~same_group)
    diff_reward = diff_group.sum(axis=(1,2))
    rewards = same_reward - diff_reward
    return np.clip(rewards/10, -1, 1)

def init_puffer(env):
    from PIL import Image
    path = os.path.join(*env.__module__.split('.')[:-1], 'pufferlib.png')
    env.puffer = np.array(Image.open(path))
    env.filled = env.puffer[:, :, 3] != 0
    env.red = (env.puffer[:, :, 0] == 255) * env.filled
    env.blue = (env.puffer[:, :, 1] == 255) * env.filled
    env.agent_red = (env.agent_colors == AGENT_1) + (env.agent_colors==AGENT_3)
    env.agent_blue = (env.agent_colors == AGENT_2) + (env.agent_colors==AGENT_4)

def reward_puffer(env):
    agent_position = env.agent_positions.astype(np.int32)
    red = env.red[agent_position[:, 0], agent_position[:, 1]]
    blue = env.blue[agent_position[:, 0], agent_position[:, 1]]
    filled_red = (red * env.agent_red).astype(bool)
    filled_blue = (blue * env.agent_blue).astype(bool)

    r = env.agent_positions[:, 0]/env.height - 0.5
    c = env.agent_positions[:, 1]/env.width - 0.5
    dist = np.sqrt(r**2 + c**2)
   
    return filled_red + filled_blue - 0.01*dist

def init_center(env):
    pass

def reward_center(env):
    r = env.agent_positions[:, 0]/env.height - 0.5
    c = env.agent_positions[:, 1]/env.width - 0.5
    return -0.01*np.sqrt(r**2 + c**2)
 
class PufferGrid(pufferlib.PufferEnv):
    def __init__(self, width=1024, height=1024, num_agents=4096,
            horizon=1024, vision_range=5, agent_speed=1.0,
            discretize=False, food_reward=0.1,
            init_fn=init_puffer, reward_fn=reward_puffer,
            expected_lifespan=1000, report_interval=32, render_mode='rgb_array'):
        super().__init__()
        self.width = width 
        self.height = height
        self.num_agents = num_agents
        self.horizon = horizon
        self.vision_range = vision_range
        self.agent_speed = agent_speed
        self.discretize = discretize
        self.food_reward = food_reward
        self.init_fn = init_fn
        self.reward_fn = reward_fn
        self.expected_lifespan = expected_lifespan
        self.report_interval = report_interval

        self.obs_size = 2*self.vision_range + 1
        self.grid = np.zeros((height, width), dtype=np.uint8)
        self.agent_positions = np.zeros((num_agents, 2), dtype=np.float32)
        self.spawn_position_cands = np.random.randint(
            vision_range, (height-vision_range, width-vision_range),
            (10*num_agents, 2)).astype(np.float32)
        self.agent_colors = np.random.randint(3, 7, num_agents, dtype=np.int32)
        self.emulated = None

        self.buf = pufferlib.namespace(
            observations = np.zeros(
                num_agents*self.obs_size*self.obs_size + 3, dtype=np.uint8),
            rewards = np.zeros(num_agents, dtype=np.float32),
            terminals = np.zeros(num_agents, dtype=bool),
            truncations = np.zeros(num_agents, dtype=bool),
            masks = np.ones(num_agents, dtype=bool),
        )
        self.actions = np.zeros(num_agents, dtype=np.uint32)
        self.episode_rewards = np.zeros((horizon, num_agents), dtype=np.float32)

        self.dones = np.ones(num_agents, dtype=bool)
        self.not_done = np.zeros(num_agents, dtype=bool)

        self.render_mode = render_mode
        if render_mode == 'human':
            COLORS = np.array([
                [6, 24, 24, 255],     # Background
                [0, 0, 255, 255],     # Food
                [0, 128, 255, 255],   # Corpse
                [128, 128, 128, 255], # Wall
                [255, 0, 0, 255],     # Snake
                [255, 255, 255, 255], # Snake
                [255, 85, 85, 255],     # Snake
                [170, 170, 170, 255], # Snake
            ], dtype=np.uint8)

            self.client = RaylibClient(80, 45, COLORS.tolist(), tile_size=16)
     
        self.observation_space = gymnasium.spaces.Box(low=0, high=255,
            shape=(self.obs_size*self.obs_size+3,), dtype=np.uint8)

        if discretize:
            self.action_space = gymnasium.spaces.MultiDiscrete([3, 3])
        else:
            finfo = np.finfo(np.float32)
            self.action_space = gymnasium.spaces.Box(
                low=finfo.min,
                high=finfo.max,
                shape=(2,),
                dtype=np.float32
            )

        self.single_observation_space = self.observation_space
        self.single_action_space = self.action_space
        self.cenv = None
        self.done = True
        self.infos = {}

    def render(self):
        grid = self.grid
        if self.render_mode == 'rgb_array':
            v = self.vision_range
            frame = COLORS[grid[v:-v-1, v:-v-1]]
            return frame

        frame, self.human_action = self.client.render(
            self.grid, self.agent_positions, self.discretize)
        return frame

    def _fill_observations(self):
        self.buf.observations[:, -3] = (255*self.agent_positions[:,0]/self.height).astype(np.uint8)
        self.buf.observations[:, -2] = (255*self.agent_positions[:,1]/self.width).astype(np.uint8)
        self.buf.observations[:, -1] = (255*self.buf.rewards).astype(np.uint8)

    def reset(self, seed=0):
        if self.cenv is None:
            self.obs_view = self.buf.observations[:, 
                :self.obs_size*self.obs_size].reshape(
                self.num_agents, self.obs_size, self.obs_size)
            
            self.cenv = CEnv(self.grid, self.agent_positions,
                self.spawn_position_cands, self.agent_colors, self.obs_view,
                self.buf.rewards, self.width, self.height, self.num_agents,
                self.horizon, self.vision_range, self.agent_speed,
                self.discretize, self.food_reward, self.expected_lifespan)

        self.agents = [i+1 for i in range(self.num_agents)]
        self.done = False
        self.tick = 1

        self.grid.fill(EMPTY)
        self.init_fn(self)
        self.episode_rewards.fill(0)
        self.cenv.reset(seed)
        self.sum_rewards = []

        self._fill_observations()
        return self.buf.observations, self.infos

    def step(self, actions):
        if self.render_mode == 'human' and self.human_action is not None:
            print(self.human_action)
            actions[0] = self.human_action

        if self.discretize:
            actions = actions.astype(np.uint32)
        else:
            actions = np.clip(actions, -1, 1).astype(np.float32)

        self.buf.rewards.fill(0)
        self.actions = actions
        self.cenv.step(actions)

        self.buf.rewards[:] += self.reward_fn(self)
        self.buf.terminals[:] = self.not_done
        self.buf.truncations[:] = self.not_done

        infos = self.infos
        self.sum_rewards.append(self.buf.rewards.sum())

        self.tick += 1
        if self.tick % self.report_interval == 0:
            infos['reward'] = np.mean(self.sum_rewards) / self.report_interval
            self.sum_rewards = []

        self._fill_observations()
        return (self.buf.observations, self.buf.rewards,
            self.buf.terminals, self.buf.truncations, infos)

class RaylibClient:
    def __init__(self, width, height, asset_map, tile_size=16):
        self.width = width
        self.height = height
        self.asset_map = asset_map
        self.tile_size = tile_size

        from raylib import rl
        rl.InitWindow(width*tile_size, height*tile_size,
            "PufferLib Ray Grid".encode())
        rl.SetTargetFPS(15)
        self.rl = rl

        from cffi import FFI
        self.ffi = FFI()

    def _cdata_to_numpy(self):
        image = self.rl.LoadImageFromScreen()
        width, height, channels = image.width, image.height, 4
        cdata = self.ffi.buffer(image.data, width*height*channels)
        return np.frombuffer(cdata, dtype=np.uint8
            ).reshape((height, width, channels))[:, :, :3]

    def render(self, grid, agent_positions, discretize):
        rl = self.rl
        ay, ax = None, None
        if rl.IsKeyDown(rl.KEY_UP) or rl.IsKeyDown(rl.KEY_W):
            ay = 0 if discretize else -1
        if rl.IsKeyDown(rl.KEY_DOWN) or rl.IsKeyDown(rl.KEY_S):
            ay = 2 if discretize else 1
        if rl.IsKeyDown(rl.KEY_LEFT) or rl.IsKeyDown(rl.KEY_A):
            ax = 0 if discretize else -1
        if rl.IsKeyDown(rl.KEY_RIGHT) or rl.IsKeyDown(rl.KEY_D):
            ax = 2 if discretize else 1

        if ax is None and ay is None:
            action = None
        else:
            if ax is None:
                ax = 1 if discretize else 0
            if ay is None:
                ay = 1 if discretize else 0

            action = (ay, ax)

        rl.BeginDrawing()
        rl.ClearBackground(self.asset_map[0])

        ts = self.tile_size
        main_r, main_c = agent_positions[0]
        main_r = int(main_r)
        main_c = int(main_c)
        r_min = main_r - self.height//2
        r_max = main_r + self.height//2
        c_min = main_c - self.width//2
        c_max = main_c + self.width//2

        for i, r in enumerate(range(r_min, r_max+1)):
            for j, c in enumerate(range(c_min, c_max+1)):
                if (r < 0 or r >= grid.shape[0] or c < 0 or c >= grid.shape[1]):
                    continue

                tile = grid[r, c]
                if tile == 0:
                    continue

                rl.DrawRectangle(j*ts, i*ts, ts, ts, self.asset_map[tile])

        rl.EndDrawing()
        return self._cdata_to_numpy(), action

def test_puffer_performance(timeout):
    import time
    env = PufferGrid()
    actions = np.random.randn(1000, env.num_agents, 2)
    idx = 0
    dones = {1: True}
    start = time.time()
    while time.time() - start < timeout:
        if env.done:
            env.reset()
            dones = {1: False}
        else:
            _, _, dones, _, _ = env.step(actions[idx%1000])

        idx += 1

    sps = env.num_agents * idx // timeout
    print(f'Puffer SPS: {sps}')

if __name__ == '__main__':
    # Run with c profile
    #from cProfile import run
    #run('test_puffer_performance(10)', sort='tottime')
    #exit(0)

    test_puffer_performance(10)