#!/usr/bin/env python3
"""
Statistics calculator for soil analysis pipeline.
"""

import logging
import time
import random
from typing import Dict, List, Tuple, Optional, Any
import pandas as pd
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import geopandas as gpd
from shapely.geometry import Point

class StatisticsCalculator:
    """
    Handles statistical analysis, sampling, and clustering for soil samples.
    """
    
    def __init__(self, logger: logging.Logger):
        """
        Initialize the statistics calculator.
        
        Args:
            logger: Logger instance for logging operations
        """
        self.logger = logger
        self.random_seed = 42
        random.seed(self.random_seed)
        np.random.seed(self.random_seed)
    
    def calculate_country_statistics(self, soil_samples_df: pd.DataFrame, 
                                   countries_df: pd.DataFrame,
                                   sampling_method: str = 'random',
                                   sample_size: int = 100,
                                   min_samples_per_country: int = 10) -> List[Dict[str, Any]]:
        """
        Calculate statistics for each country using specified sampling method.
        
        Args:
            soil_samples_df: DataFrame with soil sample data
            countries_df: DataFrame with country data
            sampling_method: 'random', 'clustering', or 'single_cluster'
            sample_size: Target sample size per country
            min_samples_per_country: Minimum samples required for analysis
            
        Returns:
            List of analysis result dictionaries
        """
        self.logger.logger.info(f"Starting statistical analysis with {sampling_method} sampling")
        self.logger.logger.info(f"Target sample size: {sample_size}, Min samples: {min_samples_per_country}")
        
        start_time = time.time()
        results = []
        
        try:
            # Get countries with samples
            countries_with_samples = self._get_countries_with_samples(soil_samples_df, countries_df)
            
            self.logger.logger.info(f"Found {len(countries_with_samples)} countries with samples")
            
            for country_id, country_data in countries_with_samples.items():
                country_samples = soil_samples_df[soil_samples_df['country_id'] == country_id]
                
                if len(country_samples) < min_samples_per_country:
                    self.logger.logger.warning(f"Country {country_data['name']} has only {len(country_samples)} samples (minimum: {min_samples_per_country})")
                    continue
                
                # Perform sampling
                if sampling_method == 'random':
                    sampled_ids = self._random_sampling(country_samples, sample_size)
                elif sampling_method == 'clustering':
                    sampled_ids = self._clustering_sampling(country_samples, sample_size)
                elif sampling_method == 'single_cluster':
                    sampled_ids = self._single_cluster_sampling(country_samples, sample_size)
                else:
                    raise ValueError(f"Unknown sampling method: {sampling_method}")
                
                # Calculate statistics
                stats = self._calculate_sample_statistics(country_samples, sampled_ids)
                
                # Create result
                result = {
                    'country_id': country_id,
                    'country_name': country_data['name'],
                    'country_code': country_data['iso_code'],
                    'sampling_method': sampling_method,
                    'total_samples': len(country_samples),
                    'sample_size': len(sampled_ids),
                    'soc_mean': stats['soc_mean'],
                    'soc_variance': stats['soc_variance'],
                    'clay_fraction_mean': stats['clay_fraction_mean'],
                    'sample_ids': sampled_ids
                }
                
                results.append(result)
                
                self.logger.logger.info(f"Country {country_data['name']}: {len(sampled_ids)} samples, "
                                      f"SOC mean: {stats['soc_mean']:.3f}%, "
                                      f"Clay mean: {stats['clay_fraction_mean']:.3f}")
            
            duration = time.time() - start_time
            self.logger.logger.info(f"Statistical analysis completed in {duration:.2f}s")
            self.logger.logger.info(f"Processed {len(results)} countries")
            
            return results
            
        except Exception as e:
            self.logger.logger.error(f"Error during statistical analysis: {e}")
            raise
    
    def _get_countries_with_samples(self, soil_samples_df: pd.DataFrame, 
                                  countries_df: pd.DataFrame) -> Dict[int, Dict[str, Any]]:
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
    
    def _random_sampling(self, country_samples: pd.DataFrame, sample_size: int) -> List[int]:
        """
        Perform random sampling of soil samples.
        
        Args:
            country_samples: DataFrame with samples for one country
            sample_size: Number of samples to select
            
        Returns:
            List of selected sample IDs
        """
        try:
            # Adjust sample size if we have fewer samples than requested
            actual_sample_size = min(sample_size, len(country_samples))
            
            # Perform random sampling
            sampled_indices = random.sample(range(len(country_samples)), actual_sample_size)
            sampled_ids = country_samples.iloc[sampled_indices]['id'].tolist()
            
            self.logger.logger.debug(f"Random sampling: {len(sampled_ids)} samples selected")
            return sampled_ids
            
        except Exception as e:
            self.logger.logger.error(f"Error during random sampling: {e}")
            raise
    
    def _clustering_sampling(self, country_samples: pd.DataFrame, sample_size: int) -> List[int]:
        """
        Perform clustering-based sampling of soil samples.
        Enhanced to handle large datasets and ensure balanced representation.
        
        Args:
            country_samples: DataFrame with samples for one country
            sample_size: Number of samples to select
            
        Returns:
            List of selected sample IDs
        """
        try:
            # Prepare data for clustering
            coords = country_samples[['latitude', 'longitude']].values
            
            # Enhanced cluster determination for large datasets
            if len(country_samples) > 1000:
                # For large datasets (like Belgium), use more clusters for better representation
                target_samples_per_cluster = 150
                n_clusters = max(5, min(sample_size // 20, len(country_samples) // target_samples_per_cluster))
            else:
                # For smaller datasets, use standard approach
                n_clusters = min(sample_size, len(country_samples), 10)  # Max 10 clusters
            
            if n_clusters < 2:
                # Fall back to random sampling for small datasets
                return self._random_sampling(country_samples, sample_size)
            
            # Perform K-means clustering
            kmeans = KMeans(n_clusters=n_clusters, random_state=self.random_seed, n_init=10)
            cluster_labels = kmeans.fit_predict(coords)
            
            # Enhanced sampling strategy: proportional sampling from clusters
            sampled_ids = []
            cluster_sizes = []
            
            # Calculate cluster sizes
            for cluster_id in range(n_clusters):
                cluster_size = len(country_samples[cluster_labels == cluster_id])
                cluster_sizes.append(cluster_size)
            
            total_samples = sum(cluster_sizes)
            
            # Proportional sampling: larger clusters get more samples
            for cluster_id in range(n_clusters):
                cluster_samples = country_samples[cluster_labels == cluster_id]
                if len(cluster_samples) > 0:
                    # Calculate proportional sample size for this cluster
                    cluster_proportion = cluster_sizes[cluster_id] / total_samples
                    cluster_sample_size = max(1, int(sample_size * cluster_proportion))
                    
                    # Ensure we don't exceed available samples
                    cluster_sample_size = min(cluster_sample_size, len(cluster_samples))
                    
                    # Randomly select samples from this cluster
                    cluster_indices = random.sample(range(len(cluster_samples)), cluster_sample_size)
                    cluster_ids = cluster_samples.iloc[cluster_indices]['id'].tolist()
                    sampled_ids.extend(cluster_ids)
            
            # If we need more samples, add random ones from underrepresented clusters
            if len(sampled_ids) < sample_size:
                remaining_samples = country_samples[~country_samples['id'].isin(sampled_ids)]
                if len(remaining_samples) > 0:
                    additional_needed = sample_size - len(sampled_ids)
                    additional_indices = random.sample(range(len(remaining_samples)), 
                                                     min(additional_needed, len(remaining_samples)))
                    additional_ids = remaining_samples.iloc[additional_indices]['id'].tolist()
                    sampled_ids.extend(additional_ids)
            
            self.logger.logger.debug(f"Clustering sampling: {len(sampled_ids)} samples selected from {n_clusters} clusters")
            return sampled_ids
            
        except Exception as e:
            self.logger.logger.error(f"Error during clustering sampling: {e}")
            # Fall back to random sampling
            return self._random_sampling(country_samples, sample_size)
    
    def _single_cluster_sampling(self, country_samples: pd.DataFrame, sample_size: int) -> List[int]:
        """
        Sample from a single randomly selected cluster per country.
        This method meets the specific requirement: "Sample one cluster for each country".
        
        Args:
            country_samples: DataFrame with samples for one country
            sample_size: Number of samples to select
            
        Returns:
            List of selected sample IDs
        """
        try:
            # Prepare data for clustering
            coords = country_samples[['latitude', 'longitude']].values
            
            # Determine number of clusters based on sample size requirements
            # We want clusters that can provide the required sample size
            min_clusters = 2
            max_clusters = min(10, len(country_samples) // max(1, sample_size // 2))
            
            if max_clusters < min_clusters:
                # Fall back to random sampling if we can't create enough clusters
                return self._random_sampling(country_samples, sample_size)
            
            # Perform K-means clustering
            kmeans = KMeans(n_clusters=max_clusters, random_state=self.random_seed, n_init=10)
            cluster_labels = kmeans.fit_predict(coords)
            
            # Find clusters that have enough samples
            valid_clusters = []
            for cluster_id in range(max_clusters):
                cluster_samples = country_samples[cluster_labels == cluster_id]
                if len(cluster_samples) >= sample_size:
                    valid_clusters.append({
                        'cluster_id': cluster_id,
                        'sample_count': len(cluster_samples),
                        'samples': cluster_samples
                    })
            
            if not valid_clusters:
                # If no cluster has enough samples, use the largest cluster
                cluster_sizes = []
                for cluster_id in range(max_clusters):
                    cluster_size = len(country_samples[cluster_labels == cluster_id])
                    cluster_sizes.append((cluster_id, cluster_size))
                
                largest_cluster_id = max(cluster_sizes, key=lambda x: x[1])[0]
                largest_cluster_samples = country_samples[cluster_labels == largest_cluster_id]
                
                # Sample what we can from the largest cluster
                actual_sample_size = min(sample_size, len(largest_cluster_samples))
                sampled_indices = random.sample(range(len(largest_cluster_samples)), actual_sample_size)
                sampled_ids = largest_cluster_samples.iloc[sampled_indices]['id'].tolist()
                
                self.logger.logger.info(f"Single cluster sampling: {len(sampled_ids)} samples from largest cluster (cluster {largest_cluster_id})")
                return sampled_ids
            
            # Randomly select one cluster from valid clusters
            selected_cluster = random.choice(valid_clusters)
            cluster_samples = selected_cluster['samples']
            
            # Sample the required number of samples from this single cluster
            sampled_indices = random.sample(range(len(cluster_samples)), sample_size)
            sampled_ids = cluster_samples.iloc[sampled_indices]['id'].tolist()
            
            self.logger.logger.info(f"Single cluster sampling: {len(sampled_ids)} samples from cluster {selected_cluster['cluster_id']}")
            return sampled_ids
            
        except Exception as e:
            self.logger.logger.error(f"Error during single cluster sampling: {e}")
            # Fall back to random sampling
            return self._random_sampling(country_samples, sample_size)
    
    def _calculate_sample_statistics(self, country_samples: pd.DataFrame, 
                                   sample_ids: List[int]) -> Dict[str, float]:
        """
        Calculate statistics for selected samples.
        
        Args:
            country_samples: DataFrame with samples for one country
            sample_ids: List of sample IDs to include in calculation
            
        Returns:
            Dictionary with statistics
        """
        try:
            # Filter samples
            sampled_data = country_samples[country_samples['id'].isin(sample_ids)]
            
            if len(sampled_data) == 0:
                return {
                    'soc_mean': 0.0,
                    'soc_variance': 0.0,
                    'clay_fraction_mean': 0.0
                }
            
            # Calculate SOC statistics
            soc_values = sampled_data['soc_percent'].dropna()
            soc_mean = soc_values.mean() if len(soc_values) > 0 else 0.0
            soc_variance = soc_values.var() if len(soc_values) > 1 else 0.0
            
            # Calculate clay fraction mean
            clay_values = sampled_data['clay_fraction'].dropna()
            clay_fraction_mean = clay_values.mean() if len(clay_values) > 0 else 0.0
            
            return {
                'soc_mean': soc_mean,
                'soc_variance': soc_variance,
                'clay_fraction_mean': clay_fraction_mean
            }
            
        except Exception as e:
            self.logger.logger.error(f"Error calculating sample statistics: {e}")
            raise
    
    def generate_summary_report(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate a summary report of all analysis results.
        
        Args:
            results: List of analysis result dictionaries
            
        Returns:
            Dictionary with summary statistics
        """
        try:
            if not results:
                return {
                    'total_countries': 0,
                    'total_samples_analyzed': 0,
                    'overall_soc_mean': 0.0,
                    'overall_soc_variance': 0.0,
                    'overall_clay_fraction_mean': 0.0,
                    'country_summary': []
                }
            
            # Calculate overall statistics
            total_samples = sum(r['sample_size'] for r in results)
            
            # Weighted averages
            weighted_soc_sum = sum(r['soc_mean'] * r['sample_size'] for r in results)
            weighted_clay_sum = sum(r['clay_fraction_mean'] * r['sample_size'] for r in results)
            
            overall_soc_mean = weighted_soc_sum / total_samples if total_samples > 0 else 0.0
            overall_clay_fraction_mean = weighted_clay_sum / total_samples if total_samples > 0 else 0.0
            
            # Overall variance (simplified calculation)
            all_soc_values = []
            for r in results:
                # Estimate individual values for variance calculation
                estimated_values = [r['soc_mean']] * r['sample_size']
                all_soc_values.extend(estimated_values)
            
            overall_soc_variance = np.var(all_soc_values) if len(all_soc_values) > 1 else 0.0
            
            # Create country summary
            country_summary = []
            for r in results:
                country_summary.append({
                    'country_code': r['country_code'],
                    'country_name': r['country_name'],
                    'sample_size': r['sample_size'],
                    'soc_mean': r['soc_mean'],
                    'soc_variance': r['soc_variance'],
                    'clay_fraction_mean': r['clay_fraction_mean']
                })
            
            summary = {
                'total_countries': len(results),
                'total_samples_analyzed': total_samples,
                'overall_soc_mean': overall_soc_mean,
                'overall_soc_variance': overall_soc_variance,
                'overall_clay_fraction_mean': overall_clay_fraction_mean,
                'country_summary': country_summary
            }
            
            self.logger.logger.info("Summary report generated:")
            self.logger.logger.info(f"  - Countries analyzed: {summary['total_countries']}")
            self.logger.logger.info(f"  - Total samples: {summary['total_samples_analyzed']}")
            self.logger.logger.info(f"  - Overall SOC mean: {summary['overall_soc_mean']:.3f}%")
            self.logger.logger.info(f"  - Overall clay fraction mean: {summary['overall_clay_fraction_mean']:.3f}")
            
            return summary
            
        except Exception as e:
            self.logger.logger.error(f"Error generating summary report: {e}")
            raise
    
    def validate_results(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Validate analysis results and check for anomalies.
        
        Args:
            results: List of analysis result dictionaries
            
        Returns:
            Dictionary with validation information
        """
        try:
            validation_info = {
                'total_results': len(results),
                'countries_with_zero_samples': 0,
                'countries_with_low_samples': 0,
                'anomalous_soc_values': 0,
                'anomalous_clay_values': 0,
                'warnings': []
            }
            
            for result in results:
                # Check for zero samples
                if result['sample_size'] == 0:
                    validation_info['countries_with_zero_samples'] += 1
                    validation_info['warnings'].append(
                        f"Country {result['country_name']} has zero samples"
                    )
                
                # Check for low sample counts
                elif result['sample_size'] < 10:
                    validation_info['countries_with_low_samples'] += 1
                    validation_info['warnings'].append(
                        f"Country {result['country_name']} has only {result['sample_size']} samples"
                    )
                
                # Check for anomalous SOC values
                if result['soc_mean'] > 50.0 or result['soc_mean'] < 0.0:
                    validation_info['anomalous_soc_values'] += 1
                    validation_info['warnings'].append(
                        f"Country {result['country_name']} has anomalous SOC mean: {result['soc_mean']:.3f}%"
                    )
                
                # Check for anomalous clay values
                if result['clay_fraction_mean'] > 1.0 or result['clay_fraction_mean'] < 0.0:
                    validation_info['anomalous_clay_values'] += 1
                    validation_info['warnings'].append(
                        f"Country {result['country_name']} has anomalous clay fraction: {result['clay_fraction_mean']:.3f}"
                    )
            
            # Log validation results
            self.logger.logger.info("Results validation:")
            self.logger.logger.info(f"  - Total results: {validation_info['total_results']}")
            self.logger.logger.info(f"  - Countries with zero samples: {validation_info['countries_with_zero_samples']}")
            self.logger.logger.info(f"  - Countries with low samples: {validation_info['countries_with_low_samples']}")
            self.logger.logger.info(f"  - Anomalous SOC values: {validation_info['anomalous_soc_values']}")
            self.logger.logger.info(f"  - Anomalous clay values: {validation_info['anomalous_clay_values']}")
            
            if validation_info['warnings']:
                self.logger.logger.warning("Validation warnings:")
                for warning in validation_info['warnings']:
                    self.logger.logger.warning(f"  - {warning}")
            
            return validation_info
            
        except Exception as e:
            self.logger.logger.error(f"Error validating results: {e}")
            raise 