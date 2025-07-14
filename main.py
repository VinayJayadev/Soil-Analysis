#!/usr/bin/env python3
"""
Main pipeline runner for the geospatial soil analysis pipeline.
"""

import sys
import os
import argparse
import time
from datetime import datetime
from pathlib import Path

# Add src to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from src.logger import setup_logging
from src.database_manager import DatabaseManager, DatabaseLogger
from src.data_loader import SoilDataLoader
from src.overpass_client import OverpassClient
from src.spatial_processor import SpatialProcessor
from src.clustering_processor import ClusteringProcessor
from src.statistics_calculator import StatisticsCalculator

class SoilAnalysisPipeline:
    """
    Main pipeline for geospatial soil analysis.
    """
    
    def __init__(self, config: dict):
        """
        Initialize the pipeline.
        
        Args:
            config: Configuration dictionary
        """
        self.config = config
        self.run_id = f"pipeline_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        
        # Create database manager first (but without initializing logging yet)
        db_path = self.config.get('db_path', 'data/db/soil_analysis.db')
        self.db_manager = None  # Will be set after logger is created

        # Setup logging (pass db_manager=None for now)
        self.pipeline_logger = setup_logging(self.run_id, db_manager=None)
        self.db_logger = DatabaseLogger(self.pipeline_logger)

        # Now create the database manager, passing the db_logger
        self.db_manager = DatabaseManager(db_path, self.db_logger)

        # Patch the pipeline_logger to have access to db_manager for DB logging
        self.pipeline_logger.db_manager = self.db_manager

        self.logger = self.pipeline_logger.logger
        self.logger.info(f"Pipeline initialized with run ID: {self.run_id}")
    
    def run(self) -> bool:
        """
        Run the complete pipeline.
        
        Returns:
            True if successful, False otherwise
        """
        start_time = time.time()
        
        try:
            self.logger.info("Starting geospatial soil analysis pipeline")
            self.logger.info(f"Configuration: {self.config}")
            
            # Stage 1: Database Initialization
            if not self._initialize_database():
                return False
            
            # Stage 2: Data Loading
            if not self._load_soil_data():
                return False
            
            # Stage 3: Overpass API Integration
            if not self._fetch_country_boundaries():
                return False
            
            # Stage 4: Spatial Association
            if not self._perform_spatial_association():
                return False
            
            # Stage 5: Clustering
            if not self._perform_clustering():
                return False
            
            # Stage 6: Statistical Analysis
            if not self._perform_statistical_analysis():
                return False
            
            # Stage 7: Generate Reports
            if not self._generate_reports():
                return False
            
            duration = time.time() - start_time
            self.logger.info(f"Pipeline completed successfully in {duration:.2f}s")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Pipeline failed: {e}")
            import traceback
            self.logger.error(traceback.format_exc())
            return False
    
    def _initialize_database(self) -> bool:
        """Initialize the database."""
        try:
            self.logger.info("Stage 1: Database Initialization")
            
            # Create database manager
            db_path = self.config.get('db_path', 'data/db/soil_analysis.db')
            self.db_manager = DatabaseManager(db_path, self.db_logger)
            
            # Check if database already exists and has data
            if self.db_manager.database_exists_and_has_data():
                self.logger.info("Database already exists with data. Clearing for fresh run...")
                self.db_manager.clear_database()
            
            self.logger.info("Database initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Database initialization failed: {e}")
            return False
    
    def _load_soil_data(self) -> bool:
        """Load soil sample data."""
        try:
            self.logger.info("Stage 2: Data Loading")
            
            # Create data loader
            data_loader = SoilDataLoader(self.pipeline_logger, self.db_manager)
            
            # Load data
            data_file = self.config.get('data_file', 'data/eu_wosis_points.fgb')
            if not os.path.exists(data_file):
                self.logger.error(f"Data file not found: {data_file}")
                return False
            
            record_count = data_loader.load_and_store_data(data_file)
            self.logger.info(f"Loaded {record_count} soil samples")
            
            # Check for data imbalance and create warning message
            self._check_data_imbalance()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Data loading failed: {e}")
            return False
    
    def _fetch_country_boundaries(self) -> bool:
        """Fetch country boundaries from Overpass API."""
        try:
            self.logger.info("Stage 3: Overpass API Integration")
            
            # Create Overpass client
            overpass_client = OverpassClient(self.pipeline_logger)
            
            # Fetch country boundaries
            country_codes = self.config.get('country_codes', None)
            countries_gdf = overpass_client.fetch_country_boundaries(country_codes)
            
            if countries_gdf is None or countries_gdf.empty:
                self.logger.error("Failed to fetch country boundaries")
                return False
            
            # Save to database
            success = overpass_client.save_countries_to_database(self.db_manager, countries_gdf)
            if not success:
                self.logger.error("Failed to save countries to database")
                return False
            
            self.logger.info(f"Fetched and saved {len(countries_gdf)} countries")
            overpass_client.close()
            
            return True
            
        except Exception as e:
            self.logger.error(f"Overpass API integration failed: {e}")
            return False
    
    def _perform_spatial_association(self) -> bool:
        """Perform spatial association of soil samples with countries."""
        try:
            self.logger.info("Stage 4: Spatial Association")
            
            # Get data from database
            soil_samples_df = self.db_manager.get_soil_samples()
            countries_df = self.db_manager.get_countries()
            
            if len(soil_samples_df) == 0:
                self.logger.error("No soil samples found in database")
                return False
            
            if len(countries_df) == 0:
                self.logger.error("No countries found in database")
                return False
            
            # Create GeoDataFrames
            import geopandas as gpd
            from shapely import wkt
            from shapely.geometry import Point
            
            # Create point geometries for soil samples
            soil_samples_df['geometry'] = [Point(lon, lat) for lon, lat in zip(soil_samples_df['longitude'], soil_samples_df['latitude'])]
            # Set the index to the actual database IDs so spatial join uses correct IDs
            soil_samples_gdf = gpd.GeoDataFrame(soil_samples_df, geometry='geometry', crs="EPSG:4326").set_index('id')
            # Filter out countries with null boundaries and parse geometry from WKT
            countries_df = countries_df.dropna(subset=['boundary_geojson'])
            self.logger.info(f"Found {len(countries_df)} countries with valid boundaries")
            
            # Parse geometry from WKT in boundary_geojson column (remove JSON quotes first)
            import json
            countries_df['geometry'] = countries_df['boundary_geojson'].apply(lambda x: wkt.loads(json.loads(x)))
            self.logger.info(f"Geometry column created with {len(countries_df)} rows")
            self.logger.info(f"Geometry column data type: {countries_df['geometry'].dtype}")
            
            # Create GeoDataFrame with explicit geometry column
            countries_gdf = gpd.GeoDataFrame(countries_df, geometry='geometry', crs="EPSG:4326")
            self.logger.info(f"GeoDataFrame created with {len(countries_gdf)} rows and geometry column: {countries_gdf.geometry.name}")
            
            # Create spatial processor
            spatial_processor = SpatialProcessor(self.pipeline_logger)
            
            # Perform spatial association
            associations = spatial_processor.associate_samples_with_countries(
                soil_samples_gdf, countries_gdf
            )
            
            # Update database
            updated_count = self.db_manager.update_country_assignments(associations)
            self.logger.info(f"Updated {updated_count} soil samples with country assignments")
            
            # Validate associations
            validation_stats = spatial_processor.validate_spatial_associations(
                associations, soil_samples_gdf, countries_gdf
            )
            
            self.logger.info(f"Spatial association coverage: {validation_stats['coverage_percentage']:.1f}%")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Spatial association failed: {e}")
            return False
    
    def _perform_clustering(self) -> bool:
        """Perform spatial clustering of soil samples within countries."""
        try:
            self.logger.info("Stage 5: Clustering")
            
            # Get data from database
            soil_samples_df = self.db_manager.get_soil_samples()
            countries_df = self.db_manager.get_countries()
            
            if len(soil_samples_df) == 0:
                self.logger.error("No soil samples found in database")
                return False
            
            if len(countries_df) == 0:
                self.logger.error("No countries found in database")
                return False
            
            # Create clustering processor
            clustering_processor = ClusteringProcessor(self.pipeline_logger)
            
            # Get clustering parameters
            min_clusters = self.config.get('min_clusters', 2)
            max_clusters = self.config.get('max_clusters', 10)
            min_samples_per_cluster = self.config.get('min_samples_per_cluster', 5)
            
            # Perform clustering
            clustering_results = clustering_processor.perform_country_clustering(
                soil_samples_df, countries_df,
                min_clusters=min_clusters,
                max_clusters=max_clusters,
                min_samples_per_cluster=min_samples_per_cluster
            )
            
            if not clustering_results:
                self.logger.warning("No clustering results generated")
                return True
            
            # Store clusters in database
            stored_clusters = self.db_manager.store_clusters(clustering_results)
            self.logger.info(f"Stored {stored_clusters} clusters in database")
            
            # Update soil samples with cluster assignments
            updated_samples = self.db_manager.update_cluster_assignments(clustering_results)
            self.logger.info(f"Updated {updated_samples} soil samples with cluster assignments")
            
            # Validate clustering results
            validation_stats = clustering_processor.validate_clustering_results(
                clustering_results, soil_samples_df
            )
            
            self.logger.info(f"Clustering coverage: {validation_stats['clustering_coverage']:.1f}%")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Clustering failed: {e}")
            return False
    
    def _perform_statistical_analysis(self) -> bool:
        """Perform statistical analysis."""
        try:
            self.logger.info("Stage 5: Statistical Analysis")
            
            # Get data from database
            soil_samples_df = self.db_manager.get_soil_samples()
            countries_df = self.db_manager.get_countries()
            
            # Create statistics calculator
            stats_calculator = StatisticsCalculator(self.pipeline_logger)
            
            # Get analysis parameters
            sampling_method = self.config.get('sampling_method', 'random')
            sample_size = self.config.get('sample_size', 100)
            min_samples = self.config.get('min_samples_per_country', 10)
            
            # Perform analysis
            results = stats_calculator.calculate_country_statistics(
                soil_samples_df, countries_df,
                sampling_method=sampling_method,
                sample_size=sample_size,
                min_samples_per_country=min_samples
            )
            
            if not results:
                self.logger.warning("No statistical analysis results generated")
                return True
            
            # Store results in database
            analysis_results = []
            for result in results:
                analysis_results.append({
                    'country_id': result['country_id'],
                    'sampling_method': result['sampling_method'],
                    'sample_size': result['sample_size'],
                    'soc_mean': result['soc_mean'],
                    'soc_variance': result['soc_variance'],
                    'clay_fraction_mean': result['clay_fraction_mean']
                })
            
            stored_count = self.db_manager.store_analysis_results(analysis_results)
            self.logger.info(f"Stored {stored_count} analysis results")
            
            # Generate summary
            summary = stats_calculator.generate_summary_report(results)
            self.logger.info(f"Analysis summary: {summary['total_countries']} countries, "
                           f"{summary['total_samples_analyzed']} samples")
            
            # Validate results
            validation = stats_calculator.validate_results(results)
            if validation['warnings']:
                self.logger.warning(f"Found {len(validation['warnings'])} validation warnings")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Statistical analysis failed: {e}")
            return False
    
    def _generate_reports(self) -> bool:
        """Generate final reports."""
        try:
            self.logger.info("Stage 6: Generate Reports")
            
            # Get database statistics
            stats = self.db_manager.get_database_stats()
            
            # Create output directory
            output_dir = Path(self.config.get('output_dir', 'output'))
            output_dir.mkdir(exist_ok=True)
            
            # Generate summary report
            report_file = output_dir / f"pipeline_report_{self.run_id}.txt"
            with open(report_file, 'w') as f:
                f.write("Geospatial Soil Analysis Pipeline Report\n")
                f.write("=" * 50 + "\n\n")
                f.write(f"Run ID: {self.run_id}\n")
                f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                
                f.write("Database Statistics:\n")
                f.write(f"  - Soil samples: {stats['soil_samples']}\n")
                f.write(f"  - Countries: {stats['countries']}\n")
                f.write(f"  - Analysis results: {stats['analysis_results']}\n")
                f.write(f"  - Countries with samples: {stats['countries_with_samples']}\n\n")
                
                f.write("Pipeline Configuration:\n")
                for key, value in self.config.items():
                    f.write(f"  - {key}: {value}\n")
            
            self.logger.info(f"Report generated: {report_file}")
            
            return True
            
        except Exception as e:
            self.logger.error(f"Report generation failed: {e}")
            return False
    
    def _check_data_imbalance(self):
        """Check for data imbalance and warn user."""
        try:
            # Get sample counts by country
            soil_samples_df = self.db_manager.get_soil_samples()
            if soil_samples_df.empty:
                return
            
            # Count samples by country
            country_counts = soil_samples_df['country_id'].value_counts()
            total_samples = len(soil_samples_df)
            
            # Find the country with the most samples
            max_country_id = country_counts.index[0]
            max_count = country_counts.iloc[0]
            max_percentage = (max_count / total_samples) * 100
            
            # Get country name
            countries_df = self.db_manager.get_countries()
            max_country_name = countries_df[countries_df['id'] == max_country_id]['name'].iloc[0] if not countries_df.empty else f"Country {max_country_id}"
            
            # Warn if there's significant imbalance
            if max_percentage > 50:
                self.logger.warning("=" * 80)
                self.logger.warning("⚠️  DATA IMBALANCE DETECTED ⚠️")
                self.logger.warning("=" * 80)
                self.logger.warning(f"Country '{max_country_name}' has {max_count:,} samples ({max_percentage:.1f}% of total)")
                self.logger.warning("This may bias European-wide analysis results.")
                self.logger.warning("Recommendations:")
                self.logger.warning("  • Consider analyzing this country separately")
                self.logger.warning("  • Use weighted statistics for European-wide analysis")
                self.logger.warning("  • Adjust clustering parameters for large datasets")
                self.logger.warning("=" * 80)
            
            # Log sample distribution
            self.logger.info("Sample distribution by country:")
            for country_id, count in country_counts.items():
                country_name = countries_df[countries_df['id'] == country_id]['name'].iloc[0] if not countries_df.empty else f"Country {country_id}"
                percentage = (count / total_samples) * 100
                self.logger.info(f"  • {country_name}: {count:,} samples ({percentage:.1f}%)")
                
        except Exception as e:
            self.logger.error(f"Error checking data imbalance: {e}")
    
    def cleanup(self):
        """Clean up resources."""
        try:
            if hasattr(self, 'db_manager'):
                self.db_manager.close()
            self.logger.info("Pipeline cleanup completed")
        except Exception as e:
            self.logger.error(f"Cleanup failed: {e}")

def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description='Geospatial Soil Analysis Pipeline')
    parser.add_argument('--data-file', default='data/eu_wosis_points.fgb',
                       help='Path to soil data file')
    parser.add_argument('--db-path', default='data/db/soil_analysis.db',
                       help='Path to database file')
    parser.add_argument('--output-dir', default='output',
                       help='Output directory for reports')
    parser.add_argument('--sampling-method', choices=['random', 'clustering', 'single_cluster'], default='random',
                       help='Sampling method for statistical analysis')
    parser.add_argument('--sample-size', type=int, default=100,
                       help='Sample size per country')
    parser.add_argument('--min-samples', type=int, default=10,
                       help='Minimum samples per country')
    parser.add_argument('--min-clusters', type=int, default=2,
                       help='Minimum clusters per country')
    parser.add_argument('--max-clusters', type=int, default=10,
                       help='Maximum clusters per country')
    parser.add_argument('--min-samples-per-cluster', type=int, default=5,
                       help='Minimum samples per cluster')
    parser.add_argument('--country-codes', nargs='+',
                       help='Specific country codes to analyze')
    
    args = parser.parse_args()
    
    # Create configuration
    config = {
        'data_file': args.data_file,
        'db_path': args.db_path,
        'output_dir': args.output_dir,
        'sampling_method': args.sampling_method,
        'sample_size': args.sample_size,
        'min_samples_per_country': args.min_samples,
        'min_clusters': args.min_clusters,
        'max_clusters': args.max_clusters,
        'min_samples_per_cluster': args.min_samples_per_cluster,
        'country_codes': args.country_codes
    }
    
    # Run pipeline
    pipeline = SoilAnalysisPipeline(config)
    
    try:
        success = pipeline.run()
        if success:
            print("Pipeline completed successfully!")
            sys.exit(0)
        else:
            print("Pipeline failed!")
            sys.exit(1)
    finally:
        pipeline.cleanup()

if __name__ == "__main__":
    main() 