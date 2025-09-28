# -*- coding: utf-8 -*-
# -*- coding: utf-8 -*-
"""
Modified PV Calculator to use Weather API for Ethiopia Solar PV Assessment Tool
"""
import geopandas as gpd
import os
import pandas as pd
import numpy as np
import pvlib
import requests
import streamlit as st
from datetime import datetime

# REGIONAL FILE MAPPING - UPDATED WITH YOUR ACTUAL MEGA URLS
REGIONAL_FILES = {
    "north": {
        "lat_range": (12, 15),
        "lon_range": (36, 40),
        "mega_url": "https://mega.nz/file/BXsBUA7B#mbZZI30pFdW4WjHJg1BSIUdOm3QapNjGjCjuXZCXaH4",
        "description": "Northern Ethiopia (Tigray)"
    },
    "northwest": {
        "lat_range": (10, 14),
        "lon_range": (35, 39),
        "mega_url": "https://mega.nz/file/kX9QiCKR#UiEP0OXmGahpn4LOfiw_AYZv-oMkAUO3JFfNhrihJAE",
        "description": "Northwestern Ethiopia (Amhara)"
    },
    "central": {
        "lat_range": (7, 11),
        "lon_range": (37, 41),
        "mega_url": "https://mega.nz/file/1X9ARIAB#qahcHbOqhhsGOi6rgOEBBqZQ5QFZwNokeh03iAA7ank",
        "description": "Central Ethiopia (Addis Ababa, Oromia)"
    },
    "east": {
        "lat_range": (5, 12),
        "lon_range": (40, 48),
        "mega_url": "https://mega.nz/file/AWFigLzQ#frYybCR5NVosyt_XxREX3x86LHlNSQSK3DlkMfptKUw",
        "description": "Eastern Ethiopia (Somali, Afar)"
    },
    "south": {
        "lat_range": (3, 8),
        "lon_range": (34, 39),
        "mega_url": "https://mega.nz/file/NWMwBQqK#st7CeaG2oNnRiFqK99KEjEBo_jq4pzI86qMdOmK3MMw",
        "description": "Southern Ethiopia (SNNPR)"
    },
    "west": {
        "lat_range": (8, 12),
        "lon_range": (33, 37),
        "mega_url": "UPDATE_WITH_WEST_REGION_MEGA_URL",
        "description": "Western Ethiopia (Benishangul-Gumuz, Gambela)"
    }
}

def get_region_for_coordinates(lat, lon):
    """Determine which regional file to use for given coordinates"""
    for region_name, region_info in REGIONAL_FILES.items():
        lat_min, lat_max = region_info["lat_range"]
        lon_min, lon_max = region_info["lon_range"]
        
        if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
            return region_name
    
    # Default to central if no match found
    return "central"

def generate_synthetic_weather_data(lat, lon):
    """Generate realistic synthetic weather data for Ethiopia"""
    
    # Create a full year of hourly data
    dates = pd.date_range('2023-01-01', '2023-12-31 23:00:00', freq='H')
    
    # Ethiopian climate parameters based on location
    if lat > 12:  # Northern Ethiopia
        base_temp, base_ghi = 22, 2100
    elif lat < 6:  # Southern Ethiopia  
        base_temp, base_ghi = 25, 2200
    elif lon > 40:  # Eastern Ethiopia
        base_temp, base_ghi = 30, 2300
    elif lon < 36:  # Western Ethiopia
        base_temp, base_ghi = 28, 1900
    else:  # Central Ethiopia
        base_temp, base_ghi = 20, 2000
    
    # Generate temperature
    day_of_year = dates.dayofyear
    hour_of_day = dates.hour
    np.random.seed(42)  # Reproducible results
    
    seasonal_temp = base_temp + 3 * np.sin(2 * np.pi * (day_of_year - 81) / 365)
    daily_temp = 8 * np.sin(2 * np.pi * (hour_of_day - 6) / 24)
    temperature = seasonal_temp + daily_temp + np.random.normal(0, 2, len(dates))
    
    # Generate solar irradiance
    solar_elevation = np.maximum(0, np.sin(2 * np.pi * (hour_of_day - 6) / 12))
    ghi = base_ghi * solar_elevation * np.random.normal(1, 0.3, len(dates))
    ghi = np.clip(ghi, 0, None)
    
    # Estimate DNI and DHI
    dni = ghi * 0.8 
    dhi = ghi * 0.2
    
    # Wind speed
    wind_speed = 3.0 + np.random.normal(0, 1, len(dates))
    wind_speed = np.clip(wind_speed, 0.5, 15)
    
    # Create DataFrame
    weather_df = pd.DataFrame({
        'time': dates,
        'temperature': temperature,
        'ghi': ghi,
        'dni': dni,
        'dhi': dhi,
        'influx_direct': dni,
        'influx_diffuse': dhi,
        'wind_speed': wind_speed,
        'wnd100m': wind_speed
    })
    
    weather_df.set_index('time', inplace=True)
    return weather_df

# Load the shapefile of Ethiopia's woredas
def load_woredas():
    current_dir = os.path.dirname(os.path.abspath(__file__))  # modules directory
    project_dir = os.path.dirname(current_dir)  # main project directory
    
    # Create necessary directories
    os.makedirs(os.path.join(project_dir, "maps"), exist_ok=True)
    
    # Load the shapefile
    SHAPEFILE = os.path.join(project_dir, "data", "shapefiles", "eth_admbnda_adm3_csa_bofedb_2021.shp")
    woredas = gpd.read_file(SHAPEFILE)
    
    # Extract town names for dropdown selection
    town_list = sorted(woredas["ADM3_EN"].unique())
    
    return woredas, town_list


@st.cache_data(ttl=3600)
def get_weather_data(lat, lon):
    """Load weather data from regional MEGA files with improved error handling"""
    
    # Determine which regional file to use
    region = get_region_for_coordinates(lat, lon)
    region_info = REGIONAL_FILES[region]
    
    st.info(f"📍 Using weather data for {region_info['description']}")
    
    # Get the MEGA URL for this region
    mega_url = region_info["mega_url"]
    
    # Check if URL is configured
    if mega_url.startswith("UPDATE_WITH_"):
        st.warning(f"⚠️ Weather data for {region} region not configured yet. Using synthetic data.")
        return generate_synthetic_weather_data(lat, lon)
    
    try:
        import xarray as xr
        with st.spinner(f"Loading weather data for {region_info['description']}..."):
            
            # Method 1: Try direct xarray access
            try:
                dataset = xr.open_dataset(mega_url, engine='h5netcdf')
                st.success(f"✅ Direct access successful for {region}!")
                
            except Exception as direct_error:
                error_msg = str(direct_error).lower()
                
                # Check if we got HTML instead of NetCDF (common MEGA issue)
                if 'doctyp' in error_msg or 'html' in error_msg or 'not the signature' in error_msg:
                    st.info("🔄 MEGA requires download method, trying alternative approach...")
                    
                    # Method 2: Download file first, then open
                    try:
                        import requests
                        import tempfile
                        
                        # Use a session with headers to mimic browser
                        session = requests.Session()
                        session.headers.update({
                            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                        })
                        
                        # Download the file
                        response = session.get(mega_url, stream=True, timeout=30)
                        
                        if response.status_code == 200:
                            # Create temporary file
                            with tempfile.NamedTemporaryFile(delete=False, suffix='.nc') as temp_file:
                                temp_filename = temp_file.name
                                
                                # Download in chunks
                                # Download in chunks with text-based progress
                                total_size = int(response.headers.get('content-length', 0))
                                downloaded = 0
                                
                                status_placeholder = st.empty()
                                
                                for chunk in response.iter_content(chunk_size=1024*1024):
                                    if chunk:
                                        temp_file.write(chunk)
                                        downloaded += len(chunk)
                                        
                                        # Safe text-based progress
                                        if total_size > 0:
                                            progress_percent = min(100, (downloaded / total_size) * 100)
                                            status_placeholder.text(f"Downloading: {progress_percent:.1f}% ({downloaded/(1024*1024):.1f} MB)")
                                        else:
                                            status_placeholder.text(f"Downloaded: {downloaded/(1024*1024):.1f} MB")
                                
                                status_placeholder.empty()
                            
                            # Try to open the downloaded file
                            try:
                                dataset = xr.open_dataset(temp_filename, engine='h5netcdf')
                                st.success(f"✅ Downloaded and loaded weather data for {region}!")
                                
                                # Clean up temp file after successful load
                                import os
                                # Don't delete yet - xarray might need it
                                
                            except Exception as file_error:
                                # Clean up temp file
                                import os
                                try:
                                    os.unlink(temp_filename)
                                except:
                                    pass
                                
                                # Check if downloaded file is HTML (MEGA redirect page)
                                if 'doctyp' in str(file_error).lower() or 'html' in str(file_error).lower():
                                    st.warning("📄 MEGA returned a webpage instead of the data file")
                                    st.info("This can happen with large files or if the link requires confirmation")
                                    raise Exception("MEGA_HTML_REDIRECT")
                                else:
                                    raise file_error
                        else:
                            raise Exception(f"Download failed with status {response.status_code}")
                            
                    except Exception as download_error:
                        if "MEGA_HTML_REDIRECT" in str(download_error):
                            st.warning("🔗 MEGA link returned a webpage - the file may be too large or require manual download")
                            st.info("Consider uploading smaller files or using a different hosting service")
                        else:
                            st.warning(f"Download method failed: {str(download_error)}")
                        raise download_error
                else:
                    # Re-raise other types of errors
                    raise direct_error
            
            # If we get here, we have a working dataset
            # Extract data for coordinates
            nearest_x = dataset.x.sel(x=lon, method="nearest")
            nearest_y = dataset.y.sel(y=lat, method="nearest")
            location_data = dataset.sel(x=nearest_x, y=nearest_y)
            
            # Convert to dataframe
            df = location_data.to_dataframe().reset_index().set_index('time')
            
            # Add wind speed handling
            if 'wnd100m' in df.columns:
                df['wind_speed'] = df['wnd100m']
            else:
                df['wind_speed'] = 1.0
            
            # Close dataset and clean up
            dataset.close()
            
            # Clean up temp file if it exists
            try:
                if 'temp_filename' in locals():
                    import os
                    os.unlink(temp_filename)
            except:
                pass
            
            return df
            
    except Exception as e:
        error_msg = str(e)
        
        if "MEGA_HTML_REDIRECT" in error_msg:
            st.error("❌ MEGA file access issue - link may need manual verification")
        elif "timeout" in error_msg.lower():
            st.error("⏱️ Download timeout - file may be too large or connection slow")
        elif "connection" in error_msg.lower():
            st.error("🌐 Network connection issue")
        else:
            st.warning(f"Failed to load weather data: {error_msg}")
        
        st.info("🔄 Using synthetic weather data as fallback...")
        return generate_synthetic_weather_data(lat, lon)

# Function to create solar position data
def get_solar_position(lat, lon, weather_df):
    """Calculate solar position throughout the year and ensure required irradiance components."""

    # Ensure the index is a DatetimeIndex
    if not isinstance(weather_df.index, pd.DatetimeIndex):
        weather_df = weather_df.set_index(pd.to_datetime(weather_df.index))

    # Calculate solar position
    times = weather_df.index
    solar_position = pvlib.solarposition.get_solarposition(times, lat, lon)

    # Calculate GHI from available direct and diffuse components
    zenith_rad = np.radians(solar_position['zenith'])
    weather_df['ghi'] = weather_df['influx_direct'] * np.cos(zenith_rad) + weather_df['influx_diffuse']
    weather_df['ghi'] = weather_df['ghi'].clip(lower=0)  # Ensure GHI is non-negative

    # Compute DNI if missing
    if 'dni' not in weather_df:
        weather_df['dni'] = weather_df['influx_direct'].clip(lower=0)

    # Compute DHI if missing
    if 'dhi' not in weather_df:
        weather_df['dhi'] = weather_df['influx_diffuse'].clip(lower=0)

    # Ensure wind speed is available
    if 'wind_speed' not in weather_df:
        weather_df['wind_speed'] = 0  # Default to zero if missing

    # Convert temperature from Kelvin to Celsius
    if 'temperature' in weather_df.columns:
        before_mean = weather_df['temperature'].mean()
        if weather_df['temperature'].mean() > 100:  # Likely in Kelvin
            weather_df['temperature'] = weather_df['temperature'] - 273.15
            after_mean = weather_df['temperature'].mean()
            print(f"Temperature converted from Kelvin to Celsius: {before_mean:.2f}K → {after_mean:.2f}°C")
    
    # Add solar position data
    result = pd.concat([weather_df, solar_position], axis=1)
    return result

def calculate_pv_production(weather_with_solar, roof_area, efficiency=0.2, system_losses=0.14, 
                          panel_width=1.7, panel_height=1.0, spacing_factor=0.2,
                          tilt=None, azimuth=None):
    """Calculate PV production for given roof area and weather data"""
    
    # Print diagnostic information
    print("===== DIAGNOSTIC INFORMATION =====")
    print(f"Temperature range: {weather_with_solar['temperature'].min():.2f}°C to {weather_with_solar['temperature'].max():.2f}°C")
    print(f"GHI mean: {weather_with_solar['ghi'].mean():.2f} W/m²")
    print(f"DNI mean: {weather_with_solar['dni'].mean():.2f} W/m²")
    print(f"DHI mean: {weather_with_solar['dhi'].mean():.2f} W/m²")
    
    # Check solar zenith angle range (should typically be 0-90 during daylight)
    print(f"Solar zenith angle range: {weather_with_solar['zenith'].min():.2f}° to {weather_with_solar['zenith'].max():.2f}°")
    if 'apparent_zenith' in weather_with_solar.columns:
        print(f"Apparent zenith angle range: {weather_with_solar['apparent_zenith'].min():.2f}° to {weather_with_solar['apparent_zenith'].max():.2f}°")
    
    # Count daytime hours (where zenith < 90°)
    daytime_hours = (weather_with_solar['zenith'] < 90).sum()
    print(f"Number of daytime hours in dataset: {daytime_hours} (should be ~4380 for annual data)")

    # Ensure necessary columns exist
    required_columns = ['ghi', 'dni', 'dhi', 'temperature', 'wind_speed']
    # Zenith can be either 'zenith' or 'apparent_zenith'
    if 'apparent_zenith' in weather_with_solar.columns:
        required_columns.append('apparent_zenith')
    else:
        required_columns.append('zenith')
    
    # Azimuth can be either 'azimuth' or 'solar_azimuth'
    if 'azimuth' in weather_with_solar.columns:
        required_columns.append('azimuth')
    else:
        required_columns.append('solar_azimuth')
        
    for col in required_columns:
        if col not in weather_with_solar:
            raise ValueError(f"Missing required column: {col}")

    # Map column names for consistent use
    solar_zenith_col = 'apparent_zenith' if 'apparent_zenith' in weather_with_solar.columns else 'zenith'
    solar_azimuth_col = 'azimuth' if 'azimuth' in weather_with_solar.columns else 'solar_azimuth'

    # If tilt and azimuth aren't provided, use latitude-based defaults
    latitude = 0
    if 'latitude' in weather_with_solar.columns:
        latitude = weather_with_solar['latitude'].iloc[0]
    elif 'lat' in weather_with_solar.columns:
        latitude = weather_with_solar['lat'].iloc[0]
    
    if tilt is None:
        tilt = abs(latitude)  # Rule of thumb: tilt = latitude
    if azimuth is None:
        azimuth = 180 if latitude >= 0 else 0  # South-facing in Northern Hemisphere, North-facing in Southern
    
    print(f"Using tilt angle: {tilt}° and azimuth: {azimuth}°")

    # Calculate how many panels can fit
    panel_area = panel_width * panel_height
    spacing_area = panel_area * (1 + spacing_factor)  # Area including spacing
    num_panels = int(roof_area / spacing_area)

    # Calculate total panel area
    total_panel_area = num_panels * panel_area

    # Standard test conditions rating per area (W/m²)
    stc_rating_per_area = 1000 * efficiency

    # System capacity in kW
    system_capacity = total_panel_area * stc_rating_per_area / 1000
    print(f"System capacity: {system_capacity:.2f} kW from {num_panels} panels covering {total_panel_area:.2f} m²")

    # Extract weather parameters - ensure proper data types and no negatives
    temp = weather_with_solar['temperature']
    print(f"Temperature stats before use: min={temp.min():.2f}°C, mean={temp.mean():.2f}°C, max={temp.max():.2f}°C")
    
    # Validate and clean irradiance data
    ghi = weather_with_solar['ghi'].clip(lower=0)  # Clip to remove negative values
    dni = weather_with_solar['dni'].clip(lower=0)
    dhi = weather_with_solar['dhi'].clip(lower=0)
    
    # Ensure non-zero wind speed to avoid temperature model issues
    wind_speed = weather_with_solar['wind_speed']
    if wind_speed.min() <= 0:
        print(f"WARNING: Wind speed contains zero or negative values. Minimum: {wind_speed.min():.2f} m/s")
        # Apply a minimum wind speed of 0.5 m/s to avoid model issues
        wind_speed = wind_speed.clip(lower=0.5)
        print(f"Applied minimum wind speed of 0.5 m/s for temperature calculations")
    
    print(f"Wind speed stats: min={wind_speed.min():.2f}, mean={wind_speed.mean():.2f}, max={wind_speed.max():.2f} m/s")

    # Get solar position data
    solar_position = pd.DataFrame({
        'apparent_zenith': weather_with_solar[solar_zenith_col],
        'azimuth': weather_with_solar[solar_azimuth_col]
    })

    # Calculate plane of array irradiance 
    print("\nCalculating plane of array irradiance...")
    poa_irradiance = pvlib.irradiance.get_total_irradiance(
        surface_tilt=tilt,
        surface_azimuth=azimuth,
        dni=dni,
        ghi=ghi,
        dhi=dhi,
        solar_zenith=solar_position['apparent_zenith'],
        solar_azimuth=solar_position['azimuth']
    )
    
    # Check POA irradiance result
    print(f"POA irradiance stats: min={poa_irradiance['poa_global'].min():.2f}, "
          f"mean={poa_irradiance['poa_global'].mean():.2f}, "
          f"max={poa_irradiance['poa_global'].max():.2f} W/m²")

    # Calculate cell temperature using a more robust model for low wind speeds
    print("\nCalculating cell temperature...")
    # First try SAPM cell temperature model with modified parameters for stability
    cell_temperature = pvlib.temperature.sapm_cell(
        poa_irradiance['poa_global'],
        temp,
        wind_speed,
        # Modified parameters for more realistic temperatures
        a=-3.56,  # Improved coefficient based on module testing
        b=-0.075,  # Improved wind coefficient for better performance at low wind speeds
        deltaT=3.0  # Standard temperature difference
    )
    
    # Verify cell temperature results
    temp_min = cell_temperature.min()
    temp_max = cell_temperature.max()
    temp_mean = cell_temperature.mean()
    print(f"Cell temperature stats: min={temp_min:.2f}°C, mean={temp_mean:.2f}°C, max={temp_max:.2f}°C")
    
    # Safety check: If temperatures are still unreasonable, use a simpler model
    if temp_max > 100 or temp_min < -20:
        print("WARNING: Cell temperatures still unrealistic, switching to simpler temperature model")
        # Use a simple temperature model: ambient + irradiance-based increase
        cell_temperature = temp + poa_irradiance['poa_global'] * 0.025 # 25°C rise per 1000 W/m²
        cell_temperature = cell_temperature.clip(lower=-20, upper=85)  # Realistic limits
        print(f"New cell temperature stats: min={cell_temperature.min():.2f}°C, "
              f"mean={cell_temperature.mean():.2f}°C, max={cell_temperature.max():.2f}°C")

    # Calculate DC power
    print("\nCalculating DC power...")
    effective_irradiance = poa_irradiance['poa_global'].clip(lower=0)  # Ensure positive irradiance
    gamma_pdc = -0.004  # Standard temperature coefficient
    
    # FIXED: Convert system capacity from kW to W for pvwatts_dc function
    system_capacity_w = system_capacity * 1000
    # Calculate DC power with validation
    dc_power = pvlib.pvsystem.pvwatts_dc(effective_irradiance, cell_temperature, 
                                        system_capacity_w, gamma_pdc)
    
    # Check DC power results and fix any negative values
    negative_dc = (dc_power < 0).sum()
    print(f"\nDC power stats: min={dc_power.min():.2f} W, max={dc_power.max():.2f} W, mean={dc_power.mean():.2f} W")
    print(f"Number of negative DC power values: {negative_dc} (should be 0)")
    
    if negative_dc > 0:
        print("WARNING: Negative DC power values detected, clipping to zero")
        dc_power = dc_power.clip(lower=0)
    
    # Apply system losses
    ac_power = dc_power * (1 - system_losses)
    
    # Calculate energy in kWh
    energy_per_hour = ac_power / 1000  # Convert W to kW
    
    # Calculate daily and monthly energy
    daily_energy = energy_per_hour.resample('D').sum()
    monthly_energy = energy_per_hour.resample('ME').sum()  # Using 'ME' instead of deprecated 'M'
    annual_energy = energy_per_hour.sum()
    
    # Calculate capacity factor
    hours_per_year = len(energy_per_hour)
    capacity_factor = annual_energy / (system_capacity * hours_per_year) * 100  # Convert to percentage
    
    # Calculate average daily production
    avg_daily_production = annual_energy / 365
    
    # Print final results
    print(f"Annual energy: {annual_energy:.2f} kWh")
    print(f"Capacity factor: {capacity_factor:.2f}%")
    print(f"Average daily production: {avg_daily_production:.2f} kWh/day")
    
    # Return results
    results = {
        'system_capacity_kw': system_capacity,
        'num_panels': num_panels,
        'annual_energy_kwh': annual_energy,
        'monthly_energy_kwh': monthly_energy.to_dict(),  # Convert to dictionary
        'avg_daily_production_kwh': avg_daily_production,
        'capacity_factor': capacity_factor,
        'hourly_ac_power': ac_power
    }
    return results


