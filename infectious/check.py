import networkx as nx
import alternative_graph
print(nx.les_miserables_graph)
print(nx.karate_club_graph)
import networkx as nx
import random


import networkx as nx
import random
import matplotlib.pyplot as plt


def random_social_graph():
    """Create a random graph representing social relationships."""
    random.seed(20)

    G = nx.Graph()

    # Add 40 nodes
    num_nodes = 40
    G.add_nodes_from(range(num_nodes))

    # Add 80 edges with random weights
    num_edges = 80
    while len(G.edges) < num_edges:
        # Randomly select two nodes
        u = random.randint(0, num_nodes - 1)
        v = random.randint(0, num_nodes - 1)

        # Ensure that the edge does not already exist
        if u != v and not G.has_edge(u, v):
            weight = random.randint(1, 10)  # Random weight between 1 and 10
            G.add_edge(u, v, weight=weight)

    return G


# Create the graph with a fixed seed for reproducibility
seed_value = 42  # You can change this to any integer
G = random_social_graph()

# Draw the graph
plt.figure(figsize=(10, 10))
pos = nx.spring_layout(G)
nx.draw(G, pos, with_labels=True, node_size=500, node_color="lightblue", font_size=10, font_weight="bold",
        edge_color="gray")
edge_labels = nx.get_edge_attributes(G, 'weight')
nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels)
plt.title("Random Social Graph")
plt.show()

nx.karate_club_graph()
