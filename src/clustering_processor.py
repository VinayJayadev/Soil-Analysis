#!/usr/bin/env python3
"""
Clustering processor for soil sample spatial clustering within countries.
"""

import logging
import time
from typing import Dict, List, Tuple, Optional
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import random

class ClusteringProcessor:
    """
    Handles spatial clustering of soil samples within countries.
    """
    
    def __init__(self, logger: logging.Logger, random_seed: int = 42):
        """
        Initialize the clustering processor.
        
        Args:
            logger: Logger instance for logging operations
            random_seed: Random seed for reproducible results
        """
        self.logger = logger
        self.random_seed = random_seed
        random.seed(random_seed)
        np.random.seed(random_seed)
    
    def perform_country_clustering(self, soil_samples_df: pd.DataFrame, 
                                 countries_df: pd.DataFrame,
                                 min_clusters: int = 2,
                                 max_clusters: int = 10,
                                 min_samples_per_cluster: int = 5) -> Dict[int, List[Dict]]:
        """
        Perform clustering on soil samples within each country.
        
        Args:
            soil_samples_df: DataFrame with soil sample data
            countries_df: DataFrame with country data
            min_clusters: Minimum number of clusters per country
            max_clusters: Maximum number of clusters per country
            min_samples_per_cluster: Minimum samples required per cluster
            
        Returns:
            Dictionary mapping country IDs to list of cluster data
        """
        self.logger.logger.info("Starting spatial clustering of soil samples within countries")
        
        start_time = time.time()
        all_clusters = {}
        
        try:
            # Get countries with samples
            countries_with_samples = self._get_countries_with_samples(soil_samples_df, countries_df)
            
            self.logger.logger.info(f"Found {len(countries_with_samples)} countries for clustering")
            
            for country_id, country_data in countries_with_samples.items():
                country_samples = soil_samples_df[soil_samples_df['country_id'] == country_id]
                
                if len(country_samples) < min_samples_per_cluster * min_clusters:
                    self.logger.logger.warning(f"Country {country_data['name']} has insufficient samples for clustering: {len(country_samples)}")
                    continue
                
                # Perform clustering for this country
                clusters = self._cluster_country_samples(country_samples, country_id, country_data,
                                                       min_clusters, max_clusters, min_samples_per_cluster)
                
                if clusters:
                    all_clusters[country_id] = clusters
                    self.logger.logger.info(f"Country {country_data['name']}: {len(clusters)} clusters created")
            
            duration = time.time() - start_time
            total_clusters = sum(len(clusters) for clusters in all_clusters.values())
            
            self.logger.logger.info(f"Clustering completed in {duration:.2f}s")
            self.logger.logger.info(f"Created {total_clusters} clusters across {len(all_clusters)} countries")
            
            return all_clusters
            
        except Exception as e:
            self.logger.logger.error(f"Error during clustering: {e}")
            raise
    
    def _get_countries_with_samples(self, soil_samples_df: pd.DataFrame, 
                                  countries_df: pd.DataFrame) -> Dict[int, Dict[str, any]]:
        """
        Get countries that have soil samples.
        
        Args:
            soil_samples_df: DataFrame with soil sample data
            countries_df: DataFrame with country data
            
        Returns:
            Dictionary mapping country IDs to country data
        """
        try:
            # Get unique country IDs that have samples
            country_ids = soil_samples_df['country_id'].dropna().unique()
            
            countries_with_samples = {}
            for country_id in country_ids:
                country_row = countries_df[countries_df['id'] == country_id]
                if not country_row.empty:
                    countries_with_samples[country_id] = {
                        'name': country_row.iloc[0]['name'],
                        'iso_code': country_row.iloc[0]['iso_code']
                    }
            
            return countries_with_samples
            
        except Exception as e:
            self.logger.logger.error(f"Error getting countries with samples: {e}")
            raise
    
    def _cluster_country_samples(self, country_samples: pd.DataFrame, country_id: int,
                               country_data: Dict, min_clusters: int, max_clusters: int,
                               min_samples_per_cluster: int) -> List[Dict]:
        """
        Perform clustering on samples from a specific country.
        
        Args:
            country_samples: DataFrame with samples for one country
            country_id: Country ID
            country_data: Country metadata
            min_clusters: Minimum number of clusters
            max_clusters: Maximum number of clusters
            min_samples_per_cluster: Minimum samples per cluster
            
        Returns:
            List of cluster data dictionaries
        """
        try:
            # Prepare coordinates for clustering
            coords = country_samples[['latitude', 'longitude']].values
            
            # Determine optimal number of clusters
            n_clusters = self._determine_optimal_clusters(coords, min_clusters, max_clusters, min_samples_per_cluster)
            
            if n_clusters < min_clusters:
                self.logger.logger.warning(f"Country {country_data['name']}: insufficient samples for clustering")
                return []
            
            # Perform K-means clustering
            kmeans = KMeans(n_clusters=n_clusters, random_state=self.random_seed, n_init=10)
            cluster_labels = kmeans.fit_predict(coords)
            
            # Create cluster data
            clusters = []
            for cluster_id in range(n_clusters):
                cluster_mask = cluster_labels == cluster_id
                cluster_samples = country_samples[cluster_mask]
                
                if len(cluster_samples) < min_samples_per_cluster:
                    continue
                
                # Calculate cluster center
                center_lat = cluster_samples['latitude'].mean()
                center_lon = cluster_samples['longitude'].mean()
                
                # Get sample IDs in this cluster
                sample_ids = cluster_samples['id'].tolist()
                
                cluster_data = {
                    'country_id': country_id,
                    'cluster_number': cluster_id + 1,  # 1-based numbering
                    'center_latitude': center_lat,
                    'center_longitude': center_lon,
                    'sample_count': len(cluster_samples),
                    'sample_ids': sample_ids
                }
                
                clusters.append(cluster_data)
            
            return clusters
            
        except Exception as e:
            self.logger.logger.error(f"Error clustering samples for country {country_data['name']}: {e}")
            return []
    
    def _determine_optimal_clusters(self, coords: np.ndarray, min_clusters: int, 
                                  max_clusters: int, min_samples_per_cluster: int) -> int:
        """
        Determine the optimal number of clusters using elbow method and sample constraints.
        Enhanced to handle large datasets (like Belgium) better.
        
        Args:
            coords: Coordinate array
            min_clusters: Minimum number of clusters
            max_clusters: Maximum number of clusters
            min_samples_per_cluster: Minimum samples per cluster
            
        Returns:
            Optimal number of clusters
        """
        try:
            n_samples = len(coords)
            
            # Enhanced max clusters calculation for large datasets
            if n_samples > 1000:
                # For large datasets (like Belgium), use more clusters to prevent oversized clusters
                # Target: 100-200 samples per cluster for optimal representation
                target_samples_per_cluster = 150
                adjusted_max = max(max_clusters, n_samples // target_samples_per_cluster)
                max_possible_clusters = min(adjusted_max, n_samples // min_samples_per_cluster)
            else:
                max_possible_clusters = min(max_clusters, n_samples // min_samples_per_cluster)
            
            if max_possible_clusters < min_clusters:
                return 0
            
            # Use elbow method to find optimal number of clusters
            inertias = []
            k_range = range(min_clusters, max_possible_clusters + 1)
            
            for k in k_range:
                kmeans = KMeans(n_clusters=k, random_state=self.random_seed, n_init=10)
                kmeans.fit(coords)
                inertias.append(kmeans.inertia_)
            
            # Simple elbow detection (find the point where inertia reduction slows down)
            if len(inertias) < 2:
                return min_clusters
            
            # Calculate the rate of change in inertia
            inertia_changes = [inertias[i-1] - inertias[i] for i in range(1, len(inertias))]
            
            # Find the elbow point (where the rate of change decreases significantly)
            if len(inertia_changes) > 1:
                change_ratios = [inertia_changes[i] / inertia_changes[i-1] if inertia_changes[i-1] > 0 else 1 
                               for i in range(1, len(inertia_changes))]
                
                # Find the first point where the ratio is less than 0.5 (significant slowdown)
                for i, ratio in enumerate(change_ratios):
                    if ratio < 0.5:
                        optimal_k = k_range[i + 1]
                        break
                else:
                    optimal_k = max_possible_clusters
            else:
                optimal_k = min_clusters
            
            # Additional check: ensure cluster sizes are reasonable for large datasets
            avg_cluster_size = n_samples / optimal_k
            if n_samples > 1000 and avg_cluster_size > 300:
                # If average cluster size is too large, increase number of clusters
                additional_clusters = int(avg_cluster_size // 200)  # Target ~200 samples per cluster
                optimal_k = min(optimal_k + additional_clusters, max_possible_clusters)
            
            return optimal_k
            
        except Exception as e:
            self.logger.logger.error(f"Error determining optimal clusters: {e}")
            return min_clusters
    
    def validate_clustering_results(self, clustering_results: Dict[int, List[Dict]], 
                                  soil_samples_df: pd.DataFrame) -> Dict[str, any]:
        """
        Validate clustering results and provide statistics.
        
        Args:
            clustering_results: Dictionary of clustering results
            soil_samples_df: DataFrame with soil sample data
            
        Returns:
            Dictionary with validation statistics
        """
        try:
            total_clusters = sum(len(clusters) for clusters in clustering_results.values())
            total_samples_clustered = sum(sum(len(cluster['sample_ids']) for cluster in clusters) 
                                        for clusters in clustering_results.values())
            
            # Calculate cluster size statistics
            cluster_sizes = []
            for clusters in clustering_results.values():
                for cluster in clusters:
                    cluster_sizes.append(cluster['sample_count'])
            
            validation_stats = {
                'total_countries': len(clustering_results),
                'total_clusters': total_clusters,
                'total_samples_clustered': total_samples_clustered,
                'avg_cluster_size': np.mean(cluster_sizes) if cluster_sizes else 0,
                'min_cluster_size': min(cluster_sizes) if cluster_sizes else 0,
                'max_cluster_size': max(cluster_sizes) if cluster_sizes else 0,
                'clustering_coverage': (total_samples_clustered / len(soil_samples_df)) * 100
            }
            
            self.logger.logger.info("Clustering validation:")
            self.logger.logger.info(f"  - Countries clustered: {validation_stats['total_countries']}")
            self.logger.logger.info(f"  - Total clusters: {validation_stats['total_clusters']}")
            self.logger.logger.info(f"  - Samples clustered: {validation_stats['total_samples_clustered']}")
            self.logger.logger.info(f"  - Coverage: {validation_stats['clustering_coverage']:.1f}%")
            self.logger.logger.info(f"  - Avg cluster size: {validation_stats['avg_cluster_size']:.1f}")
            
            return validation_stats
            
        except Exception as e:
            self.logger.logger.error(f"Error validating clustering results: {e}")
            raise 