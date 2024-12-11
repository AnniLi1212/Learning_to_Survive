import os
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
import json
import torch
from datetime import datetime
import gymnasium as gym
from src import SurvivalGameEnv, DQNAgent
import pygame
from PIL import Image
import yaml 

class Visualizer:
    def __init__(self, save_dir):
        self.save_dir = save_dir
        os.makedirs(self.save_dir, exist_ok=True)

    def plot_training_curves(self, tensorboard_log_dir):
        event_acc = EventAccumulator(tensorboard_log_dir)
        event_acc.Reload()

        tags = event_acc.Tags()['scalars']
        
        fig, axes = plt.subplots(2, 2, figsize=(15, 12))
        fig.suptitle('Training Progress', fontsize=16)
        
        if 'Train/Episode_Reward' in tags:
            rewards = [(s.step, s.value) for s in event_acc.Scalars('Train/Episode_Reward')]
            steps, values = zip(*rewards)
            axes[0, 0].plot(steps, values)
            axes[0, 0].set_title('Training Rewards')
            axes[0, 0].set_xlabel('Episode')
            axes[0, 0].set_ylabel('Reward')
            
        if 'Eval/Average_Reward' in tags:
            eval_rewards = [(s.step, s.value) for s in event_acc.Scalars('Eval/Average_Reward')]
            steps, values = zip(*eval_rewards)
            axes[0, 1].plot(steps, values)
            axes[0, 1].set_title('Evaluation Rewards')
            axes[0, 1].set_xlabel('Episode')
            axes[0, 1].set_ylabel('Average Reward')
            
        if 'Train/Health' in tags:
            health = [(s.step, s.value) for s in event_acc.Scalars('Train/Health')]
            steps, values = zip(*health)
            axes[1, 0].plot(steps, values)
            axes[1, 0].set_title('Agent Health')
            axes[1, 0].set_xlabel('Episode')
            axes[1, 0].set_ylabel('Health')
            
        if 'Train/Average_Loss' in tags:
            losses = [(s.step, s.value) for s in event_acc.Scalars('Train/Average_Loss')]
            steps, values = zip(*losses)
            axes[1, 1].plot(steps, values)
            axes[1, 1].set_title('Training Loss')
            axes[1, 1].set_xlabel('Episode')
            axes[1, 1].set_ylabel('Loss')
            
        plt.tight_layout()
        plt.savefig(os.path.join(self.save_dir, 'training_curves.png'))
        plt.close()

    def create_episode_video(self, env, agent, save_path):
        try:
            import cv2
            frames = []
            state, info = env.reset()
            done = False
            truncated = False
            total_reward = 0
            
            while not (done or truncated):
                try:
                    frame = env.render()
                    if frame is not None:
                        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                        font = cv2.FONT_HERSHEY_SIMPLEX
                        cv2.putText(frame, f'Health: {info["health"]:.1f}', 
                                (10, 20), font, 0.5, (0, 0, 0), 1)
                        cv2.putText(frame, f'Hunger: {info["hunger"]:.1f}', 
                                (10, 40), font, 0.5, (0, 0, 0), 1)
                        cv2.putText(frame, f'Attack: {info["attack"]:.1f}', 
                                (10, 60), font, 0.5, (0, 0, 0), 1)
                        cv2.putText(frame, f'Reward: {total_reward:.1f}', 
                                (10, 80), font, 0.5, (0, 0, 0), 1)
                    
                        frames.append(frame)
                    
                    if info is None:
                        info = env.unwrapped._get_info()

                    action = agent.select_action(state, info=info, training=False)
                    next_state, reward, done, truncated, next_info = env.step(action)
                    total_reward += reward
                    
                    state = next_state
                    info = next_info
                except Exception as e:
                    print(f"Warning: Error during episode recording: {str(e)}")
                    break
            
            if frames:
                height, width, _ = frames[0].shape
                fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                out = cv2.VideoWriter(save_path, fourcc, 5.0, (width, height))
                
                for frame in frames:
                    out.write(frame)
                
                out.release()
                print(f"Video saved to: {save_path}")
            
            else:
                print("Warning: No frames were captured")

        except Exception as e:
            print(f"Warning: Failed to create video: {str(e)}")
            if 'out' in locals():
                out.release()

    def visualize_value_function(self, agent, save_path):
        grid_size = agent.state_shape[0]
        states = np.zeros((grid_size * grid_size, *agent.state_shape))
        for i in range(grid_size):
            for j in range(grid_size):
                idx = i * grid_size + j
                states[idx, i, j] = 4
        
        states_tensor = torch.from_numpy(states).float().to(agent.device)
        additional_state = torch.ones(len(states), 3).to(agent.device)
        
        with torch.no_grad():
            values = agent.policy_net(states_tensor, additional_state).max(1)[0].cpu().numpy()
        
        value_grid = values.reshape((grid_size, grid_size))
        
        # heatmap
        plt.figure(figsize=(10, 8))
        sns.heatmap(value_grid, cmap='viridis')
        plt.title('State Value Function')
        plt.xlabel('X Position')
        plt.ylabel('Y Position')
        
        plt.tight_layout()
        plt.savefig(save_path)
        plt.close()

    def plot_action_distribution(self, eval_results_path):
        with open(eval_results_path, 'r') as f:
            results = json.load(f)
        
        all_actions = []
        for episode in results['results']:
            all_actions.extend(episode['actions'])
        
        plt.figure(figsize=(10, 6))
        action_counts = np.bincount(all_actions)
        action_names = ['Stay', 'Up', 'Down', 'Left', 'Right']
        
        plt.bar(action_names, action_counts)
        plt.title('Distribution of Actions During Evaluation')
        plt.xlabel('Action')
        plt.ylabel('Count')
        plt.xticks(rotation=45)
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.save_dir, 'action_distribution.png'))
        plt.close()

    def plot_state_heatmap(self, eval_results_path):
        with open(eval_results_path, 'r') as f:
            results = json.load(f)
        
        grid_size = results['config']['environment'].get('size', 16)
    
        positions = []
        for episode in results['results']:
            for state in episode['states']:
                state_array = np.array(state)
                agent_pos = np.where(state_array == 4)
                if len(agent_pos[0]) > 0:
                    x, y = agent_pos[0][0], agent_pos[1][0]
                    positions.append((x, y))
        
        plt.figure(figsize=(10, 10))
        position_counts = np.zeros((grid_size, grid_size))
        for x, y in positions:
            position_counts[x, y] += 1
        
        if position_counts.max() > 0:
            position_counts = position_counts / position_counts.max()
    
        sns.heatmap(position_counts, cmap='YlOrRd')
        plt.title('Agent Position Heatmap')
        plt.xlabel('X Position')
        plt.ylabel('Y Position')
        
        plt.tight_layout()
        plt.savefig(os.path.join(self.save_dir, 'state_heatmap.png'))
        plt.close()


def main(tensorboard_log_dir, eval_results_path, model_path, save_dir=None, timestamp=None):
    if eval_results_path and os.path.exists(eval_results_path):
        with open(eval_results_path, 'r') as f:
            eval_data = json.load(f)
            config = eval_data['config']
    else:
        print("Warning: No evaluation results found, using default config")
        config = {'environment': {}, 'agent': {}}
    if save_dir is None and timestamp is not None:
        save_dir = os.path.join("results/evaluation", f"experiment_{timestamp}")
    
    visualizer = Visualizer(save_dir)
    grid_size = config['environment'].get('size', 16)

    if tensorboard_log_dir and os.path.exists(tensorboard_log_dir):
        print("Plotting training curves...")
        visualizer.plot_training_curves(tensorboard_log_dir)
    else:
        print("Skipping training curves (no tensorboard logs available)")
    
    print("Plotting action distribution and state heatmap...")
    if eval_results_path and os.path.exists(eval_results_path):
        visualizer.plot_action_distribution(eval_results_path)
        visualizer.plot_state_heatmap(eval_results_path)
    else:
        print(f"Warning: Evaluation results not found at {eval_results_path}")
    
    if model_path and os.path.exists(model_path):
        print("Creating episode video...")
        env = gym.make('SurvivalGame-v0', 
                      render_mode='rgb_array',
                      size=grid_size,
                      max_steps=config['environment'].get('max_steps', 1000),
                      num_food=config['environment'].get('num_food', 10),
                      num_threats=config['environment'].get('num_threats', 5),
                      food_value_min=config['environment'].get('food_value_min', 10),
                      food_value_max=config['environment'].get('food_value_max', 30),
                      threat_attack_min=config['environment'].get('threat_attack_min', 20),
                      threat_attack_max=config['environment'].get('threat_attack_max', 40),
                      agent_attack_min=config['environment'].get('agent_attack_min', 30),
                      agent_attack_max=config['environment'].get('agent_attack_max', 50),
                      hungry_decay=config['environment'].get('hungry_decay', 2),
                      observation_range=config['environment'].get('observation_range', 4),
                      threat_perception_range=config['environment'].get('threat_perception_range', 2))
        
        agent = DQNAgent(
            state_shape=env.observation_space.shape,
            action_space=env.action_space,
            config=config['agent']
        )
        agent.load(model_path)

        video_path = os.path.join(visualizer.save_dir, 'episode.mp4')
        visualizer.create_episode_video(env, agent, video_path)
        
        print("Visualizing value function...")
        value_path = os.path.join(visualizer.save_dir, 'value_function.png')
        visualizer.visualize_value_function(agent, value_path)
        
        env.close()
    
    print(f"Visualizations saved to: {visualizer.save_dir}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--tensorboard-dir', type=str, required=False, default=None,
                      help='Path to tensorboard log directory')
    parser.add_argument('--eval-results', type=str, required=True,
                      help='Path to evaluation results JSON file')
    parser.add_argument('--model', type=str, default=None,
                      help='Path to model file for episode video creation')
    parser.add_argument('--save-dir', type=str, default=None,
                      help='Directory to save visualization results')
    parser.add_argument('--timestamp', type=str, default=None,
                      help='Timestamp for consistent directory naming')
    args = parser.parse_args()
    
    main(args.tensorboard_dir, args.eval_results, args.model, args.save_dir, args.timestamp)