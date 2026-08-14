import torch
import torch.nn as nn
import torch.nn.functional as F
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
import gymnasium as gym

class GraphAttentionLayer(nn.Module):
    """
    Graph Attention Layer (GAT) to dynamically weigh incoming traffic from neighbors.
    Crucial for prioritizing emergency vehicles or sudden traffic surges from specific roads.
    """
    def __init__(self, in_features, out_features, dropout=0.2, alpha=0.2):
        super(GraphAttentionLayer, self).__init__()
        self.in_features = in_features
        self.out_features = out_features
        
        self.W = nn.Linear(in_features, out_features, bias=False)
        self.a = nn.Linear(2 * out_features, 1, bias=False)
        
        self.leakyrelu = nn.LeakyReLU(alpha)
        self.dropout = nn.Dropout(dropout)

    def forward(self, h, adj):
        # h: (batch, N, in_features)
        batch_size, N, _ = h.size()
        Wh = self.W(h) # (batch, N, out_features)
        
        # Broadcasting to compute attention scores for all pairs
        Wh_repeated_in_chunks = Wh.repeat_interleave(N, dim=1)
        Wh_repeated_alternating = Wh.repeat(1, N, 1)
        
        a_input = torch.cat([Wh_repeated_in_chunks, Wh_repeated_alternating], dim=2)
        a_input = a_input.view(batch_size, N, N, 2 * self.out_features)
        
        e = self.leakyrelu(self.a(a_input).squeeze(3)) # (batch, N, N)
        
        # Masked attention: only consider connected neighbors
        zero_vec = -9e15 * torch.ones_like(e)
        attention = torch.where(adj > 0, e, zero_vec)
        attention = F.softmax(attention, dim=2)
        attention = self.dropout(attention)
        
        # Aggregate
        h_prime = torch.bmm(attention, Wh)
        return F.elu(h_prime)

class SpatioTemporalMARLExtractor(BaseFeaturesExtractor):
    """
    Spatio-Temporal GAT + LSTM Feature Extractor.
    Designed for Independent Learning with Parameter Sharing (MARL).
    
    Observation Space (Dict):
    - 'temporal_graph': Shape (T, N_nodes, Feature_dim) -> History of the local neighborhood
    - 'adjacency': Shape (N_nodes, N_nodes) -> Local connections
    """
    def __init__(self, observation_space: gym.spaces.Dict, features_dim: int = 128):
        super(SpatioTemporalMARLExtractor, self).__init__(observation_space, features_dim)
        
        temp_shape = observation_space.spaces['temporal_graph'].shape
        self.seq_len = temp_shape[0] # T (e.g., 5 past steps)
        self.n_nodes = temp_shape[1]
        self.in_dim = temp_shape[2]
        
        # 1. Spatial Processing: Graph Attention
        gat_hidden = 32
        self.gat1 = GraphAttentionLayer(self.in_dim, gat_hidden)
        self.gat2 = GraphAttentionLayer(gat_hidden, gat_hidden)
        
        # 2. Temporal Processing: LSTM 
        # Processes the sequence of spatial graphs over time
        # We flatten the graph representation per timestep to feed into LSTM
        self.lstm_in_dim = self.n_nodes * gat_hidden
        self.lstm_hidden = 64
        self.lstm = nn.LSTM(
            input_size=self.lstm_in_dim, 
            hidden_size=self.lstm_hidden, 
            num_layers=1, 
            batch_first=True
        )
        
        # Final projection
        self.fc = nn.Linear(self.lstm_hidden, features_dim)

    def forward(self, observations):
        # temp_graph: (batch, T, N, F)
        temp_graph = observations['temporal_graph']
        adj = observations['adjacency'] # (batch, N, N)
        
        batch_size = temp_graph.size(0)
        
        # We need to process each timestep through the GAT
        # Reshape to merge batch and time: (batch*T, N, F)
        x = temp_graph.view(batch_size * self.seq_len, self.n_nodes, self.in_dim)
        
        # Repeat adj for each timestep: (batch*T, N, N)
        adj_t = adj.repeat_interleave(self.seq_len, dim=0)
        
        # Apply GAT (Spatial Message Passing)
        x = self.gat1(x, adj_t)
        x = self.gat2(x, adj_t)
        
        # Flatten nodes for LSTM: (batch*T, N * gat_hidden)
        x = x.view(batch_size, self.seq_len, self.lstm_in_dim)
        
        # Apply LSTM (Temporal Processing)
        # We only care about the final hidden state of the sequence
        lstm_out, (h_n, c_n) = self.lstm(x)
        
        # h_n shape: (num_layers, batch, hidden_size)
        final_state = h_n[-1]
        
        return torch.relu(self.fc(final_state))
