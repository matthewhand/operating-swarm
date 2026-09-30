# ComfyUI Setup for Avatar Generation

This document explains how to set up ComfyUI for generating avatar images for blueprints in Operating Swarm.

## Prerequisites

1. **ComfyUI Installation**: You need ComfyUI installed and running
2. **Python Dependencies**: The `requests` library (already included in Django)
3. **Model Checkpoints**: At least one stable diffusion model checkpoint

## Installation

### 1. Install ComfyUI

```bash
# Clone ComfyUI repository
git clone https://github.com/comfyanonymous/ComfyUI.git
cd ComfyUI

# Install dependencies
pip install -r requirements.txt

# Download a model checkpoint (example)
wget https://huggingface.co/runwayml/stable-diffusion-v1-5/resolve/main/v1-5-pruned.safetensors -O models/checkpoints/stable-diffusion-v1-5.safetensors
```

### 2. Configure Environment Variables

Add these to your `.env` file:

```bash
# ComfyUI Configuration
COMFYUI_ENABLED=true
COMFYUI_HOST=http://localhost:8188
```

### 3. Start ComfyUI

```bash
# Start ComfyUI server
python main.py --listen 0.0.0.0 --port 8188
```

## Configuration

### Model Checkpoints

The avatar generation workflow uses the following checkpoint by default:
- `realisticVisionV51_v51VAE.safetensors`

You can modify the workflow in `src/swarm/utils/comfyui_client.py` to use different models.

### Avatar Styles

Available avatar styles:
- **professional**: Professional headshot style
- **cartoon**: Cartoon character style
- **anime**: Anime character style
- **realistic**: Realistic portrait style
- **icon**: Simple icon style

## Usage

### 1. Creating Blueprints with Avatars

When creating a new blueprint:
1. Check "Generate an avatar image for this blueprint"
2. Select your preferred avatar style
3. Submit the form

### 2. Generating Avatars for Existing Blueprints

1. Go to the Blueprint Library
2. Click the "Generate Avatar" button on any blueprint card
3. Choose your preferred style
4. Wait for generation to complete

### 3. API Endpoints

- `GET /blueprint-library/comfyui-status/` - Check ComfyUI availability
- `POST /blueprint-library/generate-avatar/<blueprint_name>/` - Generate avatar

## Troubleshooting

### ComfyUI Not Available

1. Check if ComfyUI is running: `curl http://localhost:8188/api/object_info`
2. Verify the `COMFYUI_HOST` environment variable
3. Check ComfyUI logs for errors

### Avatar Generation Fails

1. Ensure you have a compatible model checkpoint
2. Check ComfyUI output directory permissions
3. Verify the workflow configuration in `comfyui_client.py`

### Image Not Found

1. Check if the generated image exists in `/tmp/ComfyUI/output/`
2. Verify avatar storage directory permissions
3. Check the avatar file path in the response

## Customization

### Modifying Avatar Prompts

Edit the `_create_avatar_prompt` method in `comfyui_client.py` to customize:
- Style-specific prompts
- Category-specific elements
- Negative prompts

### Changing the Workflow

Modify the `_create_avatar_workflow` method to:
- Use different models
- Adjust generation parameters
- Add custom nodes

### Avatar Storage

Avatars are stored in the `avatars/` directory in your project root. You can customize:
- Storage location via `AVATAR_STORAGE_PATH` setting
- URL prefix via `AVATAR_URL_PREFIX` setting
- File naming convention

## Security Considerations

1. **Input Validation**: Avatar generation accepts user input for prompts
2. **File Permissions**: Ensure proper permissions on avatar storage directory
3. **Rate Limiting**: Consider implementing rate limiting for avatar generation
4. **Model Safety**: Use safe models and implement content filtering if needed

## Performance

- Avatar generation typically takes 30-60 seconds
- Consider implementing caching for generated avatars
- Monitor ComfyUI resource usage during generation

