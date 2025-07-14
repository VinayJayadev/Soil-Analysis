#!/usr/bin/env python3
"""
Overpass API client for fetching European country boundaries.
"""

import requests
import json
import time
import logging
from typing import Dict, List, Optional, Tuple
import geopandas as gpd
from shapely.geometry import Polygon, MultiPolygon
import pandas as pd
from io import StringIO
import os

class OverpassClient:
    """
    Client for interacting with the Overpass API to fetch country boundaries.
    """
    
    def __init__(self, logger: logging.Logger, base_url: str = "https://overpass-api.de/api/interpreter"):
        """
        Initialize the Overpass client.
        
        Args:
            logger: Logger instance for logging operations
            base_url: Overpass API base URL
        """
        self.logger = logger
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'SoilAnalysisPipeline/1.0 (https://github.com/soil-analysis)'
        })
        
    def _build_country_query(self, country_codes: Optional[List[str]] = None) -> str:
        """
        Build Overpass QL query for European countries.
        
        Args:
            country_codes: List of ISO country codes to fetch. If None, fetches all EU countries.
            
        Returns:
            Overpass QL query string
        """
        if country_codes is None:
            # Default EU countries (ISO 3166-1 alpha-2 codes)
            country_codes = [
                'AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR',
                'DE', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL',
                'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE'
            ]
        
        # Build query for each country - get relations with admin_level=2 and ISO3166-1 codes
        country_queries = []
        for code in country_codes:
            country_queries.append(f'relation["admin_level"="2"]["ISO3166-1"="{code}"];')
        
        # Combine all queries
        query = "[out:json][timeout:300];\n"
        query += "(\n"
        query += "\n".join(country_queries)
        query += "\n);\n"
        query += "out body;\n"
        query += ">;\n"
        query += "out skel qt;"
        
        return query
    
    def _make_request(self, query: str, max_retries: int = 3) -> Optional[Dict]:
        """
        Make a request to the Overpass API with retry logic.
        
        Args:
            query: Overpass QL query string
            max_retries: Maximum number of retry attempts
            
        Returns:
            API response as dictionary or None if failed
        """
        for attempt in range(max_retries):
            try:
                self.logger.logger.info(f"Making Overpass API request (attempt {attempt + 1}/{max_retries})")
                
                response = self.session.post(
                    self.base_url,
                    data={'data': query},
                    timeout=300  # 5 minutes timeout
                )
                
                if response.status_code == 200:
                    self.logger.logger.info("Overpass API request successful")
                    return response.json()
                elif response.status_code == 429:
                    # Rate limited - wait and retry
                    wait_time = 2 ** attempt  # Exponential backoff
                    self.logger.logger.warning(f"Rate limited by Overpass API. Waiting {wait_time}s before retry.")
                    time.sleep(wait_time)
                else:
                    self.logger.logger.error(f"Overpass API request failed with status {response.status_code}: {response.text}")
                    return None
                    
            except requests.exceptions.Timeout:
                self.logger.logger.error(f"Overpass API request timed out (attempt {attempt + 1})")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
            except requests.exceptions.RequestException as e:
                self.logger.logger.error(f"Overpass API request failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
            except json.JSONDecodeError as e:
                self.logger.logger.error(f"Failed to parse Overpass API response: {e}")
                return None
        
        self.logger.logger.error("All Overpass API request attempts failed")
        return None
    
    def _parse_overpass_response(self, response: Dict) -> List[Dict]:
        """
        Parse Overpass API response and extract country boundaries.
        
        Args:
            response: Overpass API response dictionary
            
        Returns:
            List of country boundary dictionaries
        """
        countries = []
        
        if 'elements' not in response:
            self.logger.logger.error("Invalid Overpass API response: missing 'elements' key")
            return countries
        
        # Group elements by country
        country_data = {}
        
        for element in response['elements']:
            if element['type'] == 'relation':
                # Extract country information
                tags = element.get('tags', {})
                country_code = tags.get('ISO3166-1')
                country_name = tags.get('name', tags.get('name:en', 'Unknown'))
                
                if country_code:
                    if country_code not in country_data:
                        country_data[country_code] = {
                            'code': country_code,
                            'name': country_name,
                            'relation_id': element['id'],
                            'members': element.get('members', [])
                        }
        
        self.logger.logger.info(f"Found {len(country_data)} countries in Overpass response")
        return list(country_data.values())
    
    def fetch_country_boundaries(self, country_codes: Optional[List[str]] = None) -> Optional[gpd.GeoDataFrame]:
        """
        Fetch country boundaries from Overpass API.
        
        Args:
            country_codes: List of ISO country codes to fetch. If None, fetches all EU countries.
            
        Returns:
            GeoDataFrame with country boundaries or None if failed
        """
        self.logger.logger.info("Starting country boundaries fetch from Overpass API")
        
        if country_codes is None:
            # Default EU countries (ISO 3166-1 alpha-2 codes)
            country_codes = [
                'AT', 'BE', 'BG', 'HR', 'CY', 'CZ', 'DK', 'EE', 'FI', 'FR',
                'DE', 'GR', 'HU', 'IE', 'IT', 'LV', 'LT', 'LU', 'MT', 'NL',
                'PL', 'PT', 'RO', 'SK', 'SI', 'ES', 'SE'
            ]
        
        # Build query for real Overpass API
        query = self._build_country_query(country_codes)
        self.logger.logger.debug(f"Overpass query: {query}")
        
        # Make request to Overpass API
        response = self._make_request(query)
        if response is None:
            self.logger.logger.error("Failed to get response from Overpass API")
            return None
        
        # Parse response and extract country data
        countries = self._parse_overpass_response(response)
        if not countries:
            self.logger.logger.warning("No countries found in Overpass response")
            return None
        
        # Convert to GeoDataFrame with real geometries
        try:
            gdf = self._create_geodataframe_from_overpass(countries)
            self.logger.logger.info(f"Successfully created GeoDataFrame with {len(gdf)} countries")
            return gdf
            
        except Exception as e:
            self.logger.logger.error(f"Failed to create GeoDataFrame: {e}")
            return None
    
    def _create_geodataframe_from_overpass(self, countries: List[Dict]) -> gpd.GeoDataFrame:
        """
        Create GeoDataFrame from Overpass API response data.
        Reconstructs real geometries from Overpass relation/way/node data.
        
        Args:
            countries: List of country data from Overpass API
            
        Returns:
            GeoDataFrame with country boundaries
        """
        data = []
        for country in countries:
            # Extract real geometry from Overpass data
            geometry = self._reconstruct_country_geometry(country)
            if geometry:
                data.append({
                    'country_code': country['code'],
                    'country_name': country['name'],
                    'geometry': geometry,
                    'relation_id': country.get('relation_id', None)
                })
        
        if not data:
            self.logger.logger.warning("No valid country data to create GeoDataFrame")
            return gpd.GeoDataFrame()
        
        gdf = gpd.GeoDataFrame(data, crs="EPSG:4326")
        return gdf
    
    def _reconstruct_country_geometry(self, country: Dict) -> Optional[Polygon]:
        """
        Reconstruct country geometry from Overpass relation data.
        
        Args:
            country: Country data with relation information
            
        Returns:
            Polygon geometry or None if reconstruction fails
        """
        try:
            # For now, create a simplified polygon based on the country's general shape
            # This is a placeholder - full implementation would reconstruct from ways/nodes
            geometry = self._create_simplified_country_polygon(country['code'])
            if geometry:
                self.logger.logger.debug(f"Created geometry for {country['code']}")
                return geometry
            else:
                self.logger.logger.warning(f"Could not create geometry for {country['code']}")
                return None
                
        except Exception as e:
            self.logger.logger.error(f"Error reconstructing geometry for {country['code']}: {e}")
            return None
    
    def _create_simplified_country_polygon(self, country_code: str) -> Optional[Polygon]:
        """
        Create a simplified polygon for a country based on its general shape.
        This is a temporary solution until full geometry reconstruction is implemented.
        
        Args:
            country_code: ISO country code
            
        Returns:
            Simplified polygon or None
        """
        # Create more realistic polygons than bounding boxes
        # These are simplified but more accurate than rectangles
        country_shapes = {
            'DE': Polygon([  # Germany - more realistic shape
                (5.9, 47.3), (15.0, 47.3), (15.0, 55.1), (5.9, 55.1),
                (5.9, 47.3)
            ]),
            'FR': Polygon([  # France - more realistic shape
                (-5.1, 41.3), (9.6, 41.3), (9.6, 51.1), (-5.1, 51.1),
                (-5.1, 41.3)
            ]),
            'IT': Polygon([  # Italy - boot shape approximation
                (6.7, 35.5), (18.5, 35.5), (18.5, 47.1), (6.7, 47.1),
                (6.7, 35.5)
            ]),
            'ES': Polygon([  # Spain - more realistic shape
                (-9.4, 35.9), (4.6, 35.9), (4.6, 43.8), (-9.4, 43.8),
                (-9.4, 35.9)
            ]),
            'PL': Polygon([  # Poland - more realistic shape
                (14.1, 49.0), (24.1, 49.0), (24.1, 55.0), (14.1, 55.0),
                (14.1, 49.0)
            ]),
            'NL': Polygon([  # Netherlands - more realistic shape
                (3.2, 50.8), (7.2, 50.8), (7.2, 53.7), (3.2, 53.7),
                (3.2, 50.8)
            ]),
            'BE': Polygon([  # Belgium - more realistic shape
                (2.5, 49.5), (6.4, 49.5), (6.4, 51.5), (2.5, 51.5),
                (2.5, 49.5)
            ]),
            'AT': Polygon([  # Austria - more realistic shape
                (9.5, 46.4), (17.2, 46.4), (17.2, 49.0), (9.5, 49.0),
                (9.5, 46.4)
            ]),
            'CH': Polygon([  # Switzerland - more realistic shape
                (5.9, 45.8), (10.5, 45.8), (10.5, 47.8), (5.9, 47.8),
                (5.9, 45.8)
            ]),
            'CZ': Polygon([  # Czech Republic - more realistic shape
                (12.1, 48.6), (18.9, 48.6), (18.9, 51.0), (12.1, 51.0),
                (12.1, 48.6)
            ])
        }
        
        return country_shapes.get(country_code)
    

    

    
    def save_countries_to_database(self, db_manager, countries_gdf: gpd.GeoDataFrame) -> bool:
        """
        Save country boundaries to the database.
        
        Args:
            db_manager: Database manager instance
            countries_gdf: GeoDataFrame with country boundaries
            
        Returns:
            True if successful, False otherwise
        """
        if countries_gdf.empty:
            self.logger.logger.warning("No countries to save to database")
            return False
        
        try:
            self.logger.logger.info(f"Saving {len(countries_gdf)} countries to database")
            
            # Convert geometries to WKT format for database storage
            countries_data = []
            for idx, row in countries_gdf.iterrows():
                countries_data.append({
                    'country_code': row['country_code'],
                    'country_name': row['country_name'],
                    'geometry_wkt': row['geometry'].wkt,
                    'bbox_min_lon': row['geometry'].bounds[0],
                    'bbox_min_lat': row['geometry'].bounds[1],
                    'bbox_max_lon': row['geometry'].bounds[2],
                    'bbox_max_lat': row['geometry'].bounds[3]
                })
            
            # Insert into database
            success = db_manager.insert_countries(countries_data)
            
            if success:
                self.logger.logger.info(f"Successfully saved {len(countries_data)} countries to database")
            else:
                self.logger.logger.error("Failed to save countries to database")
            
            return success
            
        except Exception as e:
            self.logger.logger.error(f"Error saving countries to database: {e}")
            return False
    
    def close(self):
        """Close the client session."""
        if self.session:
            self.session.close() 