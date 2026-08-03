from PIL import Image
import numpy as np
import os
# Open the image (ensure it's in RGBA mode)
image_name = 'tree-pressed.png'
image = Image.open(image_name).convert("RGBA")


# Define a function to convert RGBA to Hex (if needed)
#def rgba_to_hex(r, g, b, a):
 #   return f'#{r:02x}{g:02x}{b:02x}{a:02x}'


# Get the width and height of the image
width, height = image.size
print(width, height)

# Loop over all pixels in the image
for x in range(width):
    for y in range(height):
        # Get the current RGBA pixel (tuple of 4 values)
        current_pixel = image.getpixel((x, y))
        print(current_pixel)
        # Modify the color and alpha (example: change red component to 255)
        r, g, b, a = current_pixel
        original_pixel = (33, 115, 70, 255)
        updated_pixel = (0, 114, 206, 255)
        new_pixel = []

        # Uses the percent distance to 49 on the original picture to find the new RBG values
        for i in range(len(current_pixel)-1):
            try:
                percent = np.abs(original_pixel[i] - current_pixel[i])/\
                    abs(original_pixel[i] - 49)
                dist = round(np.abs(updated_pixel[i] - 49) * percent)
                if original_pixel[i] > 49:
                    new_pixel.append(updated_pixel[i] - dist)
                else:
                    new_pixel.append(updated_pixel[i] + dist)
            except ZeroDivisionError:
                new_pixel.append(current_pixel[i])

        # Assigns new RGB values
        r = new_pixel[0]  # You can adjust this as needed
        g = new_pixel[1]
        b = new_pixel[2]


        # Set the pixel back with the new RGBA values
        image.putpixel((x, y), (r, g, b, a))

# Delete current image
if os.path.exists(image_name):
    os.remove(image_name)
    image.save(image_name)
# Save the modified image
#image.save('modified_image.png')

# Show the modified image
image.show()
