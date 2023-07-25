import math
import torch

try:
    from kornia.geometry.conversions import (
        convert_points_to_homogeneous,
        convert_points_from_homogeneous,
    )
except:
    pass 
    # print('Warning: kornia is not installed. This package is only required by CaDDN')


def project_to_image(project, points, bmm=False):
    """
    Project points to image
    Args:
        project [torch.tensor(..., 3, 4)]: Projection matrix
        points [torch.Tensor(..., 3)]: 3D points
    Returns:
        points_img [torch.Tensor(..., 2)]: Points in image
        points_depth [torch.Tensor(...)]: Depth of each point
    """
    # Reshape tensors to expected shape
    points = convert_points_to_homogeneous(points)
    if not bmm:
        points = points.unsqueeze(dim=-1)
        project = project.unsqueeze(dim=1)
        
        # Transform points to image and get depths
        points_t = project @ points
        points_t = points_t.squeeze(dim=-1)
        points_depth = points_t[..., -1] - project[..., 2, 3]
    else:
        # We expand trans_01 to match the dimensions needed for bmm
        raw_shape = list(points.shape)
        raw_project = project
        points = points.reshape(-1, points.shape[-2], points.shape[-1])
        project = project.reshape(-1, project.shape[-2], project.shape[-1])
        project = project.permute(0, 2, 1)
        project = torch.repeat_interleave(project, repeats=points.shape[0] // project.shape[0], dim=0)
        points_t = torch.bmm(points, project)
        points_t = points_t.reshape(*raw_shape[:-1], 3)
        points_depth = points_t[..., -1] - raw_project[..., 2, 3]
    points_img = convert_points_from_homogeneous(points_t)
    
    return points_img, points_depth


def normalize_coords(coords, shape):
    """
    Normalize coordinates of a grid between [-1, 1]
    Args:
        coords: (..., 3), Coordinates in grid
        shape: (3), Grid shape
    Returns:
        norm_coords: (.., 3), Normalized coordinates in grid
    """
    min_n = -1
    max_n = 1
    shape = torch.flip(shape, dims=[0])  # Reverse ordering of shape

    # Subtract 1 since pixel indexing from [0, shape - 1]
    norm_coords = coords / (shape - 1) * (max_n - min_n) + min_n
    return norm_coords


def bin_depths(depth_map, mode, depth_min, depth_max, num_bins, target=False):
    """
    Converts depth map into bin indices
    Args:
        depth_map: (H, W), Depth Map
        mode: string, Discretiziation mode (See https://arxiv.org/pdf/2005.13423.pdf for more details)
            UD: Uniform discretiziation
            LID: Linear increasing discretiziation
            SID: Spacing increasing discretiziation
        depth_min: float, Minimum depth value
        depth_max: float, Maximum depth value
        num_bins: int, Number of depth bins
        target: bool, Whether the depth bins indices will be used for a target tensor in loss comparison
    Returns:
        indices: (H, W), Depth bin indices
    """
    if mode == "UD":
        bin_size = (depth_max - depth_min) / num_bins
        indices = ((depth_map - depth_min) / bin_size)
    elif mode == "LID":
        bin_size = 2 * (depth_max - depth_min) / (num_bins * (1 + num_bins))
        indices = -0.5 + 0.5 * torch.sqrt(1 + 8 * (depth_map - depth_min) / bin_size)
    elif mode == "SID":
        indices = num_bins * (torch.log(1 + depth_map) - math.log(1 + depth_min)) / \
            (math.log(1 + depth_max) - math.log(1 + depth_min))
    else:
        raise NotImplementedError

    if target:
        # Remove indicies outside of bounds
        mask = (indices < 0) | (indices > num_bins) | (~torch.isfinite(indices))
        indices[mask] = num_bins

        # Convert to integer
        indices = indices.type(torch.int64)
    return indices
