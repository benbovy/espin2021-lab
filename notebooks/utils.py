import numpy as np
import xarray as xr
import xsimlab as xs
from fastscape.models import basic_model
from fastscape.processes import SurfaceTopography, RasterGrid2D
from bmi_topography import Topography


def extract_dem(north=40.25, south=39.75, west=-105.25, east=-104.75):
    """Extract elevation data using a region of interest."""
    
    params = {
        'dem_type': 'SRTMGL3',
         'south': south,
         'north': north,
         'west': west,
         'east': east,
         'output_format': 'GTiff',
         'cache_dir': '~/.bmi_topography'
    }
    
    topo = Topography(**params)

    print("Fetch topographic data...")
    topo.fetch()

    print("Load dataset...")
    return topo.load()


@xs.process
class InitDEM:
    dem = xs.variable(dims=('y', 'x'))
    elevation = xs.foreign(SurfaceTopography, 'elevation', intent='out')
    
    def initialize(self):
        self.elevation = self.dem
        

model = basic_model.update_processes({'init_topography': InitDEM})


def run_fastscape_model(dem, scheduler, store, U=1e-5, K=[2e-6, 4e-6, 8e-6, 1.6e-5], m=0.5, n=1, D=1e-2):
    
    resolution = 90
    grid_shape = [dem.sizes['y'], dem.sizes['x']]
    grid_length = list(np.array(grid_shape) * resolution)

    in_ds = xs.create_setup(
        model=model,
        clocks={
            'time': np.arange(0, 1e6 + 1e4, 2e4),
            'out': np.arange(0, 1e6 + 1e4, 2e4),
        },
        master_clock='time',
        input_vars={
            'grid__shape': grid_shape,
            'grid__length': grid_length,
            'boundary__status': 'fixed_value',
            'init_topography__dem': dem.squeeze().astype('d'),
            'uplift__rate': U,
            'spl': {
                'k_coef': ('batch', K),
                'area_exp': m,
                'slope_exp': n
            },
            'diffusion__diffusivity': D
        },
        output_vars={
            'topography__elevation': 'out',
            'drainage__area': 'out',
        }
    )
    
    out_ds = (
        in_ds
        .xsimlab.run(
            model=model, batch_dim="batch", parallel=True, scheduler=scheduler, store=store
        )
        .set_index(batch="spl__k_coef")
        .assign_coords(x=dem.x, y=dem.y)
    )
    
    return out_ds