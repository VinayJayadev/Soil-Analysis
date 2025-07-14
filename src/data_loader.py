"""
Data loader for the geospatial soil analysis pipeline.
Handles loading and parsing of soil sample data from .fgb files.
"""

import geopandas as gpd
import pandas as pd
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from logger import PipelineLogger
from database_manager import DatabaseManager, DatabaseLogger


class SoilDataLoader:
    """
    Loads and processes soil sample data from .fgb files.
    """
    
    def __init__(self, pipeline_logger: PipelineLogger, db_manager: DatabaseManager):
        """
        Initialize the data loader.
        
        Args:
            pipeline_logger: Main pipeline logger
            db_manager: Database manager instance
        """
        self.pipeline_logger = pipeline_logger
        self.db_manager = db_manager
        self.db_logger = DatabaseLogger(pipeline_logger)
    
    def load_soil_data(self, file_path: str) -> pd.DataFrame:
        """
        Load soil sample data from .fgb file and prepare for database insertion.
        
        Args:
            file_path: Path to the .fgb file
            
        Returns:
            DataFrame with processed soil sample data
        """
        self.pipeline_logger.log_stage_start("Data Loading", f"Loading soil samples from {file_path}")
        
        try:
            # Load the .fgb file
            self.pipeline_logger.logger.debug(f"Loading soil samples from: {file_path}")
            gdf = gpd.read_file(file_path)
            
            # Set CRS if not already set
            if gdf.crs is None:
                gdf.set_crs(epsg=4326, inplace=True)
                self.pipeline_logger.logger.debug("Set CRS to EPSG:4326")
            
            # Extract coordinates
            gdf['latitude'] = gdf.geometry.y
            gdf['longitude'] = gdf.geometry.x
            
            # Parse SOC% values from JSON
            self.pipeline_logger.logger.debug("Parsing SOC% values from JSON format")
            soc_values = []
            soc_methods = []
            
            for val in gdf['soc_percent']:
                try:
                    if pd.notna(val) and str(val) != 'nan':
                        if isinstance(val, str):
                            parsed = json.loads(val)
                        else:
                            parsed = val
                        
                        if 'value' in parsed:
                            soc_values.append(float(parsed['value']))
                            soc_methods.append(parsed.get('method', ''))
                        else:
                            soc_values.append(0.0)
                            soc_methods.append('')
                    else:
                        soc_values.append(0.0)
                        soc_methods.append('')
                except Exception as e:
                    self.pipeline_logger.log_warning(f"Failed to parse SOC% value: {val}", f"Error: {str(e)}")
                    soc_values.append(0.0)
                    soc_methods.append('')
            
            # Update the GeoDataFrame with parsed values
            gdf['soc_percent_parsed'] = soc_values
            gdf['soc_method'] = soc_methods
            
            # Estimate clay fraction based on SOC% (placeholder approach)
            self.pipeline_logger.logger.debug("Estimating clay fraction based on SOC%")
            clay_fractions = []
            for soc_val in soc_values:
                clay_fractions.append(self._estimate_clay_fraction(soc_val))
            
            gdf['clay_fraction'] = clay_fractions
            
            # Prepare DataFrame for database insertion
            df = pd.DataFrame({
                'raw_data_id': gdf['raw_data_id'],
                'latitude': gdf['latitude'],
                'longitude': gdf['longitude'],
                'soc_percent': gdf['soc_percent_parsed'],
                'soc_method': gdf['soc_method'],
                'top_depth_cm': gdf['top_depth_cm'],
                'bottom_depth_cm': gdf['bottom_depth_cm'],
                'sampling_date': gdf['sampling_date'],
                'lab_analysis_date': gdf['lab_analysis_date'],
                'clay_fraction': gdf['clay_fraction']
            })
            
            # Validate data
            self._validate_data(df)
            
            # Log data loading statistics
            record_count = len(df)
            self.pipeline_logger.logger.info(f"Loaded {record_count:,} soil samples")
            self.pipeline_logger.logger.info(f"Successfully parsed {record_count:,} SOC% values")
            
            # Log SOC% statistics
            soc_stats = df['soc_percent'].describe()
            self.pipeline_logger.logger.info(f"SOC% range: {soc_stats['min']:.3f}% - {soc_stats['max']:.3f}%")
            self.pipeline_logger.logger.info(f"Mean SOC%: {soc_stats['mean']:.3f}%")
            
            # Log clay fraction statistics
            clay_stats = df['clay_fraction'].describe()
            self.pipeline_logger.logger.info(f"Clay fraction range: {clay_stats['min']:.3f} - {clay_stats['max']:.3f}")
            self.pipeline_logger.logger.info(f"Mean clay fraction: {clay_stats['mean']:.3f}")
            
            return df
            
        except Exception as e:
            self.pipeline_logger.log_error(e, f"Failed to load soil data from {file_path}", "Data Loading")
            raise
    
    def _estimate_clay_fraction(self, soc_percent: float) -> float:
        """
        Estimate clay fraction based on SOC% (placeholder approach).
        
        Args:
            soc_percent: Soil organic carbon percentage
            
        Returns:
            Estimated clay fraction (0.0 to 1.0)
        """
        # Simple estimation based on SOC% ranges
        # This is a placeholder approach as mentioned in the requirements
        if soc_percent < 1.0:
            return 0.15  # Low SOC = sandy soil
        elif soc_percent < 3.0:
            return 0.25  # Medium SOC = loamy soil
        else:
            return 0.35  # High SOC = clay soil
    
    def _validate_data(self, df: pd.DataFrame):
        """
        Validate the loaded data for quality and completeness.
        
        Args:
            df: DataFrame to validate
        """
        self.pipeline_logger.logger.debug("Validating data quality")
        
        # Check for missing values
        missing_counts = df.isnull().sum()
        if missing_counts.sum() > 0:
            self.pipeline_logger.log_warning(f"Found missing values: {missing_counts.to_dict()}")
        
        # Check coordinate ranges
        lat_range = (df['latitude'].min(), df['latitude'].max())
        lon_range = (df['longitude'].min(), df['longitude'].max())
        
        if not (-90 <= lat_range[0] <= 90 and -90 <= lat_range[1] <= 90):
            self.pipeline_logger.log_warning(f"Latitude out of valid range: {lat_range}")
        
        if not (-180 <= lon_range[0] <= 180 and -180 <= lon_range[1] <= 180):
            self.pipeline_logger.log_warning(f"Longitude out of valid range: {lon_range}")
        
        # Check SOC% range
        soc_range = (df['soc_percent'].min(), df['soc_percent'].max())
        if soc_range[0] < 0 or soc_range[1] > 100:
            self.pipeline_logger.log_warning(f"SOC% out of expected range: {soc_range}")
        
        # Check depth ranges
        depth_range = (df['top_depth_cm'].min(), df['bottom_depth_cm'].max())
        if depth_range[0] < 0 or depth_range[1] > 1000:
            self.pipeline_logger.log_warning(f"Depth out of expected range: {depth_range}")
        
        self.pipeline_logger.logger.debug("Data validation completed")
    
    def load_and_store_data(self, file_path: str) -> int:
        """
        Load soil data and store it in the database.
        
        Args:
            file_path: Path to the .fgb file
            
        Returns:
            Number of records stored
        """
        start_time = time.time()
        
        try:
            # Load and process data
            df = self.load_soil_data(file_path)
            
            # Store in database
            record_count = self.db_manager.insert_soil_samples(df)
            
            duration = time.time() - start_time
            self.pipeline_logger.log_stage_complete("Data Loading", {
                "records": record_count,
                "duration": f"{duration:.1f}s",
                "file": Path(file_path).name
            })
            
            return record_count
            
        except Exception as e:
            self.pipeline_logger.log_error(e, "Data loading and storage failed", "Data Loading")
            raise


class DataValidator:
    """
    Validates data quality and provides data quality reports.
    """
    
    def __init__(self, pipeline_logger: PipelineLogger):
        """
        Initialize the data validator.
        
        Args:
            pipeline_logger: Main pipeline logger
        """
        self.pipeline_logger = pipeline_logger
    
    def generate_data_quality_report(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Generate a comprehensive data quality report.
        
        Args:
            df: DataFrame to analyze
            
        Returns:
            Dictionary with data quality metrics
        """
        self.pipeline_logger.logger.debug("Generating data quality report")
        
        report = {
            "total_records": len(df),
            "missing_values": df.isnull().sum().to_dict(),
            "coordinate_ranges": {
                "latitude": (df['latitude'].min(), df['latitude'].max()),
                "longitude": (df['longitude'].min(), df['longitude'].max())
            },
            "soc_statistics": df['soc_percent'].describe().to_dict(),
            "clay_statistics": df['clay_fraction'].describe().to_dict(),
            "depth_ranges": {
                "top_depth": (df['top_depth_cm'].min(), df['top_depth_cm'].max()),
                "bottom_depth": (df['bottom_depth_cm'].min(), df['bottom_depth_cm'].max())
            },
            "date_ranges": {
                "sampling_date": (df['sampling_date'].min(), df['sampling_date'].max()),
                "lab_analysis_date": (df['lab_analysis_date'].min(), df['lab_analysis_date'].max())
            }
        }
        
        # Check for potential issues
        issues = []
        
        if report["missing_values"]["soc_percent"] > 0:
            issues.append(f"SOC% missing values: {report['missing_values']['soc_percent']}")
        
        if report["coordinate_ranges"]["latitude"][0] < -90 or report["coordinate_ranges"]["latitude"][1] > 90:
            issues.append("Invalid latitude range detected")
        
        if report["coordinate_ranges"]["longitude"][0] < -180 or report["coordinate_ranges"]["longitude"][1] > 180:
            issues.append("Invalid longitude range detected")
        
        if report["soc_statistics"]["min"] < 0 or report["soc_statistics"]["max"] > 100:
            issues.append("SOC% values outside expected range (0-100%)")
        
        report["issues"] = issues
        report["quality_score"] = max(0, 100 - len(issues) * 10)  # Simple quality score
        
        self.pipeline_logger.logger.info(f"Data quality score: {report['quality_score']}/100")
        if issues:
            self.pipeline_logger.logger.warning(f"Data quality issues found: {len(issues)}")
            for issue in issues:
                self.pipeline_logger.logger.warning(f"  - {issue}")
        
        return report


if __name__ == "__main__":
    # Test the data loader
    from logger import setup_logging
    from database_manager import DatabaseManager, DatabaseLogger
    
    # Setup logging
    pipeline_logger = setup_logging("data_loader_test")
    db_logger = DatabaseLogger(pipeline_logger)
    
    # Setup database
    with DatabaseManager("data/db/test.db", db_logger) as db_manager:
        # Create data loader
        data_loader = SoilDataLoader(pipeline_logger, db_manager)
        
        # Load data
        try:
            record_count = data_loader.load_and_store_data("data/eu_wosis_points.fgb")
            print(f"Successfully loaded and stored {record_count} soil samples")
        except Exception as e:
            print(f"Error loading data: {e}")
    
    print("Data loader test completed.") 