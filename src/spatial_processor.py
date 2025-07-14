#!/usr/bin/env python3
"""
Spatial processor for associating soil samples with countries.
"""

import logging
import time
from typing import Dict, List, Tuple, Optional
import geopandas as gpd
import pandas as pd
from shapely.geometry import Point
from shapely.ops import unary_union
import numpy as np

class SpatialProcessor:
    """
    Handles spatial operations for associating soil samples with countries.
    """
    
    def __init__(self, logger: logging.Logger):
        """
        Initialize the spatial processor.
        
        Args:
            logger: Logger instance for logging operations
        """
        self.logger = logger
    
    def associate_samples_with_countries(self, soil_samples_gdf: gpd.GeoDataFrame, 
                                       countries_gdf: gpd.GeoDataFrame) -> Dict[int, int]:
        """
        Associate soil samples with countries using spatial operations.
        
        Args:
            soil_samples_gdf: GeoDataFrame with soil sample points
            countries_gdf: GeoDataFrame with country boundaries
            
        Returns:
            Dictionary mapping soil sample IDs to country IDs
        """
        self.logger.logger.info("Starting spatial association of soil samples with countries")
        
        start_time = time.time()
        
        try:
            # Ensure both GeoDataFrames have the same CRS
            if soil_samples_gdf.crs != countries_gdf.crs:
                self.logger.logger.info("Reprojecting soil samples to match countries CRS")
                soil_samples_gdf = soil_samples_gdf.to_crs(countries_gdf.crs)
            
            # Create point geometries for soil samples
            self.logger.logger.info("Creating point geometries for soil samples")
            soil_points = self._create_sample_points(soil_samples_gdf)
            
            # Perform spatial join
            self.logger.logger.info("Performing spatial join (point-in-polygon)")
            associations = self._perform_spatial_join(soil_points, countries_gdf)
            
            duration = time.time() - start_time
            self.logger.logger.info(f"Spatial association completed in {duration:.2f}s")
            self.logger.logger.info(f"Associated {len(associations)} soil samples with countries")
            
            return associations
            
        except Exception as e:
            self.logger.logger.error(f"Error during spatial association: {e}")
            raise
    
    def _create_sample_points(self, soil_samples_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Create point geometries from soil sample coordinates.
        
        Args:
            soil_samples_gdf: GeoDataFrame with soil sample data
            
        Returns:
            GeoDataFrame with point geometries
        """
        try:
            # Create Point geometries from lat/lon
            points = []
            for idx, row in soil_samples_gdf.iterrows():
                point = Point(row['longitude'], row['latitude'])
                points.append(point)
            
            # Create new GeoDataFrame with points
            points_gdf = gpd.GeoDataFrame(
                soil_samples_gdf.drop(['latitude', 'longitude'], axis=1),
                geometry=points,
                crs=soil_samples_gdf.crs
            )
            
            self.logger.logger.info(f"Created {len(points_gdf)} point geometries")
            return points_gdf
            
        except Exception as e:
            self.logger.logger.error(f"Error creating sample points: {e}")
            raise
    
    def _perform_spatial_join(self, soil_points: gpd.GeoDataFrame, 
                            countries_gdf: gpd.GeoDataFrame) -> Dict[int, int]:
        """
        Perform spatial join to associate points with countries.
        
        Args:
            soil_points: GeoDataFrame with soil sample points
            countries_gdf: GeoDataFrame with country boundaries
            
        Returns:
            Dictionary mapping soil sample IDs to country IDs
        """
        try:
            # Perform spatial join
            joined = gpd.sjoin(soil_points, countries_gdf, how='left', predicate='within')
            
            # Extract associations
            associations = {}
            unassigned_count = 0
            
            for idx, row in joined.iterrows():
                soil_id = idx  # The index is the original soil sample ID
                country_index = row.get('index_right')
                
                if pd.notna(country_index):
                    # Get the actual country ID from the countries DataFrame
                    country_id = countries_gdf.iloc[int(country_index)]['id']
                    associations[soil_id] = int(country_id)
                else:
                    unassigned_count += 1
            
            # Log results
            self.logger.logger.info(f"Spatial join results:")
            self.logger.logger.info(f"  - Total samples: {len(soil_points)}")
            self.logger.logger.info(f"  - Associated: {len(associations)}")
            self.logger.logger.info(f"  - Unassigned: {unassigned_count}")
            
            if unassigned_count > 0:
                self.logger.logger.warning(f"{unassigned_count} samples could not be assigned to any country")
            
            return associations
            
        except Exception as e:
            self.logger.logger.error(f"Error during spatial join: {e}")
            raise
    
    def get_country_sample_counts(self, associations: Dict[int, int], 
                                countries_gdf: gpd.GeoDataFrame) -> Dict[str, int]:
        """
        Get sample counts per country.
        
        Args:
            associations: Dictionary mapping soil sample IDs to country IDs
            countries_gdf: GeoDataFrame with country data
            
        Returns:
            Dictionary with country codes and sample counts
        """
        try:
            # Count samples per country
            country_counts = {}
            for soil_id, country_id in associations.items():
                country_row = countries_gdf[countries_gdf['id'] == country_id]
                if not country_row.empty:
                    country_code = country_row.iloc[0]['iso_code']
                    country_counts[country_code] = country_counts.get(country_code, 0) + 1
            
            # Add countries with zero samples
            for _, country in countries_gdf.iterrows():
                country_code = country['iso_code']
                if country_code not in country_counts:
                    country_counts[country_code] = 0
            
            self.logger.logger.info(f"Sample counts per country: {country_counts}")
            return country_counts
            
        except Exception as e:
            self.logger.logger.error(f"Error calculating country sample counts: {e}")
            raise
    
    def validate_spatial_associations(self, associations: Dict[int, int], 
                                   soil_samples_gdf: gpd.GeoDataFrame,
                                   countries_gdf: gpd.GeoDataFrame) -> Dict[str, any]:
        """
        Validate spatial associations and provide statistics.
        
        Args:
            associations: Dictionary mapping soil sample IDs to country IDs
            soil_samples_gdf: GeoDataFrame with soil sample data
            countries_gdf: GeoDataFrame with country data
            
        Returns:
            Dictionary with validation statistics
        """
        try:
            total_samples = len(soil_samples_gdf)
            associated_samples = len(associations)
            unassigned_samples = total_samples - associated_samples
            
            # Calculate coverage statistics
            coverage_percentage = (associated_samples / total_samples) * 100 if total_samples > 0 else 0
            
            # Get country distribution
            country_counts = self.get_country_sample_counts(associations, countries_gdf)
            countries_with_samples = sum(1 for count in country_counts.values() if count > 0)
            
            # Calculate spatial statistics
            spatial_stats = {
                'total_samples': total_samples,
                'associated_samples': associated_samples,
                'unassigned_samples': unassigned_samples,
                'coverage_percentage': coverage_percentage,
                'countries_with_samples': countries_with_samples,
                'total_countries': len(countries_gdf),
                'country_distribution': country_counts
            }
            
            self.logger.logger.info("Spatial association validation:")
            self.logger.logger.info(f"  - Coverage: {coverage_percentage:.1f}%")
            self.logger.logger.info(f"  - Countries with samples: {countries_with_samples}")
            self.logger.logger.info(f"  - Unassigned samples: {unassigned_samples}")
            
            return spatial_stats
            
        except Exception as e:
            self.logger.logger.error(f"Error validating spatial associations: {e}")
            raise
    
    def get_unassigned_samples(self, associations: Dict[int, int], 
                             soil_samples_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Get soil samples that could not be assigned to any country.
        
        Args:
            associations: Dictionary mapping soil sample IDs to country IDs
            soil_samples_gdf: GeoDataFrame with soil sample data
            
        Returns:
            GeoDataFrame with unassigned samples
        """
        try:
            assigned_ids = set(associations.keys())
            unassigned_mask = ~soil_samples_gdf['id'].isin(assigned_ids)
            unassigned_samples = soil_samples_gdf[unassigned_mask]
            
            self.logger.logger.info(f"Found {len(unassigned_samples)} unassigned samples")
            
            if len(unassigned_samples) > 0:
                self.logger.logger.debug("Unassigned sample coordinates:")
                for idx, row in unassigned_samples.head(10).iterrows():
                    self.logger.logger.debug(f"  Sample {row['id']}: ({row['latitude']}, {row['longitude']})")
            
            return unassigned_samples
            
        except Exception as e:
            self.logger.logger.error(f"Error getting unassigned samples: {e}")
            raise
    
    def optimize_country_boundaries(self, countries_gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
        """
        Optimize country boundaries for better spatial operations.
        
        Args:
            countries_gdf: GeoDataFrame with country boundaries
            
        Returns:
            Optimized GeoDataFrame
        """
        try:
            self.logger.logger.info("Optimizing country boundaries for spatial operations")
            
            # Simplify geometries to improve performance
            simplified_geometries = []
            for idx, row in countries_gdf.iterrows():
                simplified_geom = row.geometry.simplify(tolerance=0.001)
                simplified_geometries.append(simplified_geom)
            
            # Create optimized GeoDataFrame
            optimized_gdf = gpd.GeoDataFrame(
                countries_gdf.drop('geometry', axis=1),
                geometry=simplified_geometries,
                crs=countries_gdf.crs
            )
            
            self.logger.logger.info("Country boundaries optimized")
            return optimized_gdf
            
        except Exception as e:
            self.logger.logger.error(f"Error optimizing country boundaries: {e}")
            # Return original if optimization fails
            return countries_gdf 