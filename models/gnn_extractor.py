import torch
import torch.nn as nn
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
import gymnasium as gym

class SimpleGCNLayer(nn.Module):
    """
    A simple Graph Convolutional Network (GCN) layer using raw PyTorch.
    Formula: H' = ReLU( (A + I) H W )
    """
    def __init__(self, in_features: int, out_features: int):
        super(SimpleGCNLayer, self).__init__()
        self.linear = nn.Linear(in_features, out_features)

    def forward(self, x: torch.Tensor, adj: torch.Tensor) -> torch.Tensor:
        # x: (batch_size, num_nodes, in_features)
        # adj: (batch_size, num_nodes, num_nodes)
        
        # Add self-loops: A_hat = A + I
        batch_size, num_nodes, _ = adj.shape
        identity = torch.eye(num_nodes, device=adj.device).unsqueeze(0).expand(batch_size, -1, -1)
        a_hat = adj + identity
        
        # Normalize adjacency matrix (simplified degree normalization)
        # degree = A_hat.sum(dim=-1, keepdim=True)
        # a_hat_norm = a_hat / (degree + 1e-8)
        
        # Message passing: (batch, nodes, nodes) @ (batch, nodes, features) -> (batch, nodes, features)
        msg = torch.bmm(a_hat, x)
        
        # Linear transformation
        out = self.linear(msg)
        return torch.relu(out)


class GNNExtractor(BaseFeaturesExtractor):
    """
    Custom Feature Extractor for Graph Neural Networks in Stable-Baselines3.
    
    Expects observation space to be a spaces.Dict containing:
      - 'node_features': shape (N_nodes, Feature_dim)
      - 'adjacency': shape (N_nodes, N_nodes)
    
    Produces a fixed-size vector representation of the graph, or per-node 
    representations depending on the control scheme.
    """
    def __init__(self, observation_space: gym.spaces.Dict, features_dim: int = 256):
        super(GNNExtractor, self).__init__(observation_space, features_dim)
        
        node_shape = observation_space.spaces['node_features'].shape
        self.num_nodes = node_shape[0]
        self.node_feature_dim = node_shape[1]
        
        # GNN layers
        hidden_dim = 64
        self.gcn1 = SimpleGCNLayer(self.node_feature_dim, hidden_dim)
        self.gcn2 = SimpleGCNLayer(hidden_dim, hidden_dim)
        
        # Flatten and project to requested features_dim
        # If we control all nodes centrally, we concatenate them
        # If we control one node, we would extract just that node's features.
        # Assuming centralized control for this extractor:
        self.fc = nn.Linear(self.num_nodes * hidden_dim, features_dim)
        self.relu = nn.ReLU()

    def forward(self, observations: dict) -> torch.Tensor:
        x = observations['node_features']  # (batch, n_nodes, f_dim)
        adj = observations['adjacency']    # (batch, n_nodes, n_nodes)
        
        # N-Hop Message Passing
        # Hop 1
        x = self.gcn1(x, adj)
        # Hop 2
        x = self.gcn2(x, adj)
        
        # Flatten graph representation
        batch_size = x.shape[0]
        x_flat = x.view(batch_size, -1)
        
        return self.relu(self.fc(x_flat))

