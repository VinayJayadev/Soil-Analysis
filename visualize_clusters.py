#!/usr/bin/env python3
"""
Clustering Visualization Script
Creates comprehensive visualizations of soil sample clustering results
"""

import sqlite3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import geopandas as gpd
from shapely.geometry import Point
import numpy as np
from collections import defaultdict
import warnings
warnings.filterwarnings('ignore')

class ClusterVisualizer:
    def __init__(self, db_path='data/db/soil_analysis.db'):
        self.db_path = db_path
        self.setup_plotting()
        
    def setup_plotting(self):
        """Setup matplotlib and seaborn for better visualizations"""
        # Use non-interactive backend to avoid display issues
        plt.switch_backend('Agg')
        plt.style.use('seaborn-v0_8')
        sns.set_palette("husl")
        plt.rcParams['figure.figsize'] = (12, 8)
        plt.rcParams['font.size'] = 10
        
    def get_clustering_data(self):
        """Fetch clustering data from database"""
        conn = sqlite3.connect(self.db_path)
        
        # Get cluster statistics by country
        cluster_stats = pd.read_sql_query("""
            SELECT 
                c.name as country_name,
                COUNT(cl.id) as cluster_count,
                AVG(cl.sample_count) as avg_samples_per_cluster,
                SUM(cl.sample_count) as total_samples,
                MIN(cl.sample_count) as min_cluster_size,
                MAX(cl.sample_count) as max_cluster_size
            FROM clusters cl 
            JOIN countries c ON cl.country_id = c.id 
            GROUP BY c.name 
            ORDER BY cluster_count DESC
        """, conn)
        
        # Get individual cluster data
        cluster_details = pd.read_sql_query("""
            SELECT 
                c.name as country_name,
                cl.cluster_number,
                cl.center_latitude,
                cl.center_longitude,
                cl.sample_count
            FROM clusters cl 
            JOIN countries c ON cl.country_id = c.id 
            ORDER BY c.name, cl.cluster_number
        """, conn)
        
        # Get sample distribution within clusters
        sample_distribution = pd.read_sql_query("""
            SELECT 
                c.name as country_name,
                cl.cluster_number,
                COUNT(ss.id) as actual_samples,
                AVG(ss.soc_percent) as avg_soc
            FROM clusters cl 
            JOIN countries c ON cl.country_id = c.id 
            JOIN soil_samples ss ON ss.country_id = c.id AND ss.cluster_id = cl.id
            GROUP BY c.name, cl.cluster_number
            ORDER BY c.name, cl.cluster_number
        """, conn)
        
        conn.close()
        return cluster_stats, cluster_details, sample_distribution
    
    def plot_cluster_distribution(self, cluster_stats):
        """Plot cluster distribution by country"""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        
        # Plot 1: Number of clusters by country
        colors = sns.color_palette("husl", len(cluster_stats))
        bars1 = ax1.bar(cluster_stats['country_name'], cluster_stats['cluster_count'], 
                       color=colors, alpha=0.7, edgecolor='black', linewidth=0.5)
        ax1.set_title('Number of Clusters by Country', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Country')
        ax1.set_ylabel('Number of Clusters')
        ax1.tick_params(axis='x', rotation=45)
        
        # Add value labels on bars
        for bar in bars1:
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                    f'{int(height)}', ha='center', va='bottom', fontweight='bold')
        
        # Plot 2: Average cluster size by country
        bars2 = ax2.bar(cluster_stats['country_name'], cluster_stats['avg_samples_per_cluster'], 
                       color=colors, alpha=0.7, edgecolor='black', linewidth=0.5)
        ax2.set_title('Average Samples per Cluster by Country', fontsize=14, fontweight='bold')
        ax2.set_xlabel('Country')
        ax2.set_ylabel('Average Samples per Cluster')
        ax2.tick_params(axis='x', rotation=45)
        
        # Add value labels on bars
        for bar in bars2:
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height + 5,
                    f'{height:.1f}', ha='center', va='bottom', fontweight='bold')
        
        plt.tight_layout()
        plt.savefig('output/cluster_distribution.png', dpi=300, bbox_inches='tight')
        plt.close()
        
    def plot_cluster_size_analysis(self, cluster_stats):
        """Plot cluster size analysis"""
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        
        # Plot 1: Cluster size range by country
        x_pos = np.arange(len(cluster_stats))
        width = 0.35
        
        bars1 = ax1.bar(x_pos - width/2, cluster_stats['min_cluster_size'], width, 
                       label='Min Cluster Size', alpha=0.7, color='lightblue')
        bars2 = ax1.bar(x_pos + width/2, cluster_stats['max_cluster_size'], width, 
                       label='Max Cluster Size', alpha=0.7, color='darkblue')
        
        ax1.set_title('Cluster Size Range by Country', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Country')
        ax1.set_ylabel('Number of Samples')
        ax1.set_xticks(x_pos)
        ax1.set_xticklabels(cluster_stats['country_name'], rotation=45)
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Plot 2: Total samples vs cluster count
        scatter = ax2.scatter(cluster_stats['cluster_count'], cluster_stats['total_samples'], 
                            s=cluster_stats['avg_samples_per_cluster']*2, 
                            c=range(len(cluster_stats)), cmap='viridis', alpha=0.7)
        
        # Add country labels
        for i, country in enumerate(cluster_stats['country_name']):
            ax2.annotate(country, (cluster_stats['cluster_count'].iloc[i], 
                                 cluster_stats['total_samples'].iloc[i]),
                        xytext=(5, 5), textcoords='offset points', fontsize=8)
        
        ax2.set_title('Total Samples vs Cluster Count', fontsize=14, fontweight='bold')
        ax2.set_xlabel('Number of Clusters')
        ax2.set_ylabel('Total Samples')
        ax2.grid(True, alpha=0.3)
        
        # Add colorbar
        cbar = plt.colorbar(scatter, ax=ax2)
        cbar.set_label('Average Cluster Size')
        
        plt.tight_layout()
        plt.savefig('output/cluster_size_analysis.png', dpi=300, bbox_inches='tight')
        plt.close()
        
    def plot_geographic_clusters(self, cluster_details):
        """Plot clusters on a geographic map with background"""
        try:
            import contextily as ctx
            has_contextily = True
        except ImportError:
            has_contextily = False
            print("contextily not available, using basic map")
        
        fig, ax = plt.subplots(1, 1, figsize=(16, 12))
        
        # Set map bounds with some padding
        lon_min, lon_max = cluster_details['center_longitude'].min() - 3, cluster_details['center_longitude'].max() + 3
        lat_min, lat_max = cluster_details['center_latitude'].min() - 3, cluster_details['center_latitude'].max() + 3
        
        ax.set_xlim(lon_min, lon_max)
        ax.set_ylim(lat_min, lat_max)
        
        # Add map background if contextily is available
        if has_contextily:
            try:
                # Add OpenStreetMap background
                ctx.add_basemap(ax, crs='EPSG:4326', source=ctx.providers.OpenStreetMap.Mapnik)
                print("Added OpenStreetMap background")
            except Exception as e:
                print(f"Could not load map background: {e}")
                # Fallback to basic grid
                ax.grid(True, alpha=0.3)
        else:
            # Basic grid as fallback
            ax.grid(True, alpha=0.3)
        
        # Plot clusters by country with better visibility
        countries = cluster_details['country_name'].unique()
        colors = sns.color_palette("husl", len(countries))
        
        for i, country in enumerate(countries):
            country_data = cluster_details[cluster_details['country_name'] == country]
            
            # Plot cluster centers with larger, more visible markers
            scatter = ax.scatter(country_data['center_longitude'], country_data['center_latitude'],
                               s=country_data['sample_count']/5,  # Larger size for better visibility
                               c=[colors[i]], alpha=0.8, edgecolors='black', linewidth=1.5,
                               label=f'{country} ({len(country_data)} clusters)',
                               zorder=10)  # Ensure clusters are on top
            
            # Add cluster numbers with better visibility
            for _, row in country_data.iterrows():
                ax.annotate(f'{int(row["cluster_number"])}', 
                           (row['center_longitude'], row['center_latitude']),
                           xytext=(5, 5), textcoords='offset points', 
                           fontsize=10, fontweight='bold', color='white',
                           bbox=dict(boxstyle="round,pad=0.3", facecolor='black', alpha=0.7),
                           zorder=11)  # Ensure labels are on top
        
        # Add country names at cluster centers for better identification
        for i, country in enumerate(countries):
            country_data = cluster_details[cluster_details['country_name'] == country]
            # Add country name at the center of the country's clusters
            center_lon = country_data['center_longitude'].mean()
            center_lat = country_data['center_latitude'].mean()
            
            ax.annotate(country, (center_lon, center_lat),
                       xytext=(0, 20), textcoords='offset points',
                       fontsize=12, fontweight='bold', color=colors[i],
                       ha='center', va='bottom',
                       bbox=dict(boxstyle="round,pad=0.5", facecolor='white', alpha=0.8, edgecolor=colors[i]),
                       zorder=12)
        
        ax.set_title('Geographic Distribution of Soil Sample Clusters\n(30 clusters across 8 European countries)', 
                    fontsize=16, fontweight='bold', pad=20)
        ax.set_xlabel('Longitude', fontsize=12)
        ax.set_ylabel('Latitude', fontsize=12)
        
        # Move legend outside the plot for better visibility
        ax.legend(bbox_to_anchor=(1.02, 1), loc='upper left', fontsize=10)
        
        plt.tight_layout()
        plt.savefig('output/geographic_clusters.png', dpi=300, bbox_inches='tight')
        plt.close()
        
    def plot_soc_analysis(self, sample_distribution):
        """Plot SOC analysis within clusters"""
        if sample_distribution.empty:
            print("No SOC data available for visualization")
            return
            
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 6))
        
        # Plot 1: Average SOC by cluster
        countries = sample_distribution['country_name'].unique()
        colors = sns.color_palette("husl", len(countries))
        
        for i, country in enumerate(countries):
            country_data = sample_distribution[sample_distribution['country_name'] == country]
            ax1.scatter(country_data['cluster_number'], country_data['avg_soc'],
                       s=country_data['actual_samples']/5, c=[colors[i]], alpha=0.7,
                       label=country, edgecolors='black', linewidth=0.5)
        
        ax1.set_title('Average SOC% by Cluster', fontsize=14, fontweight='bold')
        ax1.set_xlabel('Cluster Number')
        ax1.set_ylabel('Average SOC%')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
        
        # Plot 2: SOC variability by country
        country_soc_stats = sample_distribution.groupby('country_name').agg({
            'avg_soc': ['mean', 'std'],
            'actual_samples': 'sum'
        }).round(3)
        
        country_soc_stats.columns = ['mean_soc', 'std_soc', 'total_samples']
        country_soc_stats = country_soc_stats.reset_index()
        
        bars = ax2.bar(country_soc_stats['country_name'], country_soc_stats['mean_soc'],
                      alpha=0.7, color=colors[:len(country_soc_stats)], 
                      edgecolor='black', linewidth=0.5)
        
        ax2.set_title('Average SOC% by Country (with Standard Deviation)', fontsize=14, fontweight='bold')
        ax2.set_xlabel('Country')
        ax2.set_ylabel('Average SOC%')
        ax2.tick_params(axis='x', rotation=45)
        ax2.grid(True, alpha=0.3)
        
        # Add value labels
        for bar in bars:
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height + 0.01,
                    f'{height:.2f}', ha='center', va='bottom', fontweight='bold')
        
        plt.tight_layout()
        plt.savefig('output/soc_analysis.png', dpi=300, bbox_inches='tight')
        plt.close()
        
    def create_summary_report(self, cluster_stats, cluster_details, sample_distribution):
        """Create a comprehensive summary report"""
        print("=" * 80)
        print("🎯 CLUSTERING ANALYSIS SUMMARY REPORT")
        print("=" * 80)
        
        print(f"\n📊 OVERALL STATISTICS:")
        print(f"   • Total Countries: {len(cluster_stats)}")
        print(f"   • Total Clusters: {cluster_stats['cluster_count'].sum()}")
        print(f"   • Total Samples: {cluster_stats['total_samples'].sum():,}")
        print(f"   • Average Clusters per Country: {cluster_stats['cluster_count'].mean():.1f}")
        print(f"   • Average Samples per Cluster: {cluster_stats['avg_samples_per_cluster'].mean():.1f}")
        
        print(f"\n🏆 TOP PERFORMING COUNTRIES:")
        print(f"   • Most Clusters: {cluster_stats.iloc[0]['country_name']} ({cluster_stats.iloc[0]['cluster_count']} clusters)")
        print(f"   • Largest Average Cluster: {cluster_stats.loc[cluster_stats['avg_samples_per_cluster'].idxmax(), 'country_name']} ({cluster_stats['avg_samples_per_cluster'].max():.1f} samples)")
        print(f"   • Most Total Samples: {cluster_stats.loc[cluster_stats['total_samples'].idxmax(), 'country_name']} ({cluster_stats['total_samples'].max():,} samples)")
        
        print(f"\n⚠️  POTENTIAL ISSUES:")
        # Check for anomalies
        large_clusters = cluster_stats[cluster_stats['avg_samples_per_cluster'] > 100]
        small_clusters = cluster_stats[cluster_stats['avg_samples_per_cluster'] < 10]
        
        if not large_clusters.empty:
            print(f"   • Large clusters detected: {', '.join(large_clusters['country_name'].tolist())}")
        if not small_clusters.empty:
            print(f"   • Small clusters detected: {', '.join(small_clusters['country_name'].tolist())}")
            
        print(f"\n📈 CLUSTERING QUALITY METRICS:")
        print(f"   • Cluster Size CV: {cluster_stats['avg_samples_per_cluster'].std() / cluster_stats['avg_samples_per_cluster'].mean():.2f}")
        print(f"   • Geographic Coverage: {len(cluster_details)} distinct regions")
        
        if not sample_distribution.empty:
            print(f"   • SOC Data Available: Yes ({len(sample_distribution)} cluster measurements)")
            print(f"   • Average SOC%: {sample_distribution['avg_soc'].mean():.2f}%")
            print(f"   • SOC Range: {sample_distribution['avg_soc'].min():.2f}% - {sample_distribution['avg_soc'].max():.2f}%")
        
        print("\n" + "=" * 80)
        
    def generate_all_visualizations(self):
        """Generate all clustering visualizations"""
        print("🎨 Generating clustering visualizations...")
        
        # Get data
        cluster_stats, cluster_details, sample_distribution = self.get_clustering_data()
        
        # Create output directory
        import os
        os.makedirs('output', exist_ok=True)
        
        # Generate visualizations
        print("📊 Creating cluster distribution plots...")
        self.plot_cluster_distribution(cluster_stats)
        
        print("📈 Creating cluster size analysis...")
        self.plot_cluster_size_analysis(cluster_stats)
        
        print("🗺️  Creating geographic cluster map...")
        self.plot_geographic_clusters(cluster_details)
        
        print("🌱 Creating SOC analysis plots...")
        self.plot_soc_analysis(sample_distribution)
        
        # Create summary report
        print("📋 Generating summary report...")
        self.create_summary_report(cluster_stats, cluster_details, sample_distribution)
        
        print("✅ All visualizations saved to 'output/' directory!")
        print("📁 Files created:")
        print("   • cluster_distribution.png")
        print("   • cluster_size_analysis.png") 
        print("   • geographic_clusters.png")
        print("   • soc_analysis.png")

if __name__ == "__main__":
    visualizer = ClusterVisualizer()
    visualizer.generate_all_visualizations() 