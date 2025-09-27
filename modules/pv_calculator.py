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
    """Load weather data from MEGA or other direct download service"""
    
    # Example MEGA URL (replace with your actual URL)
    MEGA_URL = "https://mega.nz/file/gP0EmRJb#kLZRPsZW7EaR7d6mlEioyVHhNgU_QVGcentrQsv354w"
    
    try:
        import xarray as xr
        with st.spinner("Loading weather data from MEGA..."):
            # MEGA URLs work directly with xarray
            dataset = xr.open_dataset(MEGA_URL, engine='h5netcdf')
            
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
            
            dataset.close()
            st.success("✅ Weather data loaded successfully!")
            return df
            
    except Exception as e:
        st.warning(f"Failed to load weather data: {e}")
        st.info("Using synthetic weather data...")
        return generate_synthetic_weather_data(lat, lon)
    
    except Exception as e:
        st.error(f"Error accessing weather data: {str(e)}")
        # If direct access fails, provide fallback behavior or more detailed error
        st.error("Make sure your WEATHER_DATA_URL secret is configured correctly in Streamlit")
        raise
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

# The rest of your calculate_pv_production function remains the same
# [Include the rest of your existing function here]

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



