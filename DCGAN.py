import os
import shutil
from cleanfid import fid
import torch
import torch.nn as nn
import torchvision
from matplotlib import pyplot as plt
from torchvision.utils import save_image
import numpy as np
import random
from torchvision.datasets import CIFAR100
from torch.utils.data import DataLoader
from torchvision.transforms import Compose, ToTensor
from torch.optim import Adam, AdamW
import torchvision.utils as vutils


store_path = "dcgan_model.pt"


# helper function to make getting another batch of data easier
def cycle(iterable):
    while True:
        for x in iterable:
            yield x


# Setting reproducibility
SEED = 0
random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)

# hyperparameters
params = {
    'batch_size': 128,
    'nc': 3,
    'n_latent': 32,
    'lr': 0.002,
    'n_epochs': 50,
    'nz': 100,  # Size of z latent vector
    'real_label': 0.9,  # Label smoothing
    'fake_label': 0,
    'min_beta': 1e-4,
    'max_beta': 0.02,
    'beta1': 0.5,  # Hyperparameter for Adam
    'dim': 32,  # Image Size
    'ngf': 64,  # Size of feature maps for Generator
    'ndf': 64,  # Size of feature maps for Discriminator
    'num_workers': 2,
    'store_path': 'dcgan_model.pt'  # Store path for trained weights of model
}

device = torch.device('cuda') if torch.cuda.is_available() else torch.device('cpu')
print(f"Using device: {device}\t" + (f"{torch.cuda.get_device_name(0)}" if torch.cuda.is_available() else "CPU"))


class Generator(nn.Module):
    def __init__(self, nc, nz, ngf):
        super(Generator, self).__init__()
        self.main = nn.Sequential(
            nn.ConvTranspose2d(nz, ngf * 2, 3, 1, 0, bias=False),
            nn.BatchNorm2d(ngf * 2),
            nn.ReLU(True),
            nn.ConvTranspose2d(ngf * 2, ngf * 2, 3, 2, 1, bias=False),
            nn.BatchNorm2d(ngf * 2),
            nn.ReLU(True),
            nn.ConvTranspose2d(ngf * 2, ngf * 2, 3, 2, 1, bias=False),
            nn.BatchNorm2d(ngf * 2),
            nn.ReLU(True),
            nn.ConvTranspose2d(ngf * 2, ngf, 3, 2, 1, bias=False),
            nn.BatchNorm2d(ngf),
            nn.ReLU(True),
            nn.ConvTranspose2d(ngf, nc, 3, 2, 1, bias=False),
            nn.Tanh(),  # Signmoid as alternative
        )

    def forward(self, i):
        return self.main(i)


class Discriminator(nn.Module):
    def __init__(self, nc, ndf):
        super(Discriminator, self).__init__()
        self.main = nn.Sequential(
            nn.Conv2d(nc, ndf, 2, 2, 1, bias=False),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(ndf, ndf * 2, 3, 2, 1, bias=False),
            nn.BatchNorm2d(ndf * 2),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(ndf * 2, ndf * 2, 3, 2, 1, bias=False),
            nn.BatchNorm2d(ndf * 2),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(ndf * 2, ndf * 2, 3, 2, 1, bias=False),
            nn.BatchNorm2d(ndf * 2),
            nn.LeakyReLU(0.2, inplace=True),
            nn.Conv2d(ndf * 2, 1, 3, 1, 0, bias=False),
            nn.Sigmoid(),
        )

    def forward(self, i):
        return self.main(i)


# Weight function
def weights_init(m):
    classname = m.__class__.__name__
    if classname.find("Conv") != -1:
        nn.init.normal_(m.weight.data, 0.0, 0.02)
    elif classname.find("BatchNorm") != -1:
        nn.init.normal_(m.weight.data, 1.0, 0.02)
        nn.init.constant_(m.bias.data, 0)


# nc = params['nc']
# nz = params['nz']
# ngf = params['ngf']
# ndf = params['ndf']
# lr = params['lr']
# beta1 = params['beta1']
# n_epochs = params['n_epochs']
# batch_size = params['batch_size']
# image_size = params['dim']
# real_label = params['real_label']
# fake_label = params['fake_label']

# create/clean the directories
def setup_directory(directory):
    if os.path.exists(directory):
        shutil.rmtree(directory)  # remove any existing (old) data
    os.makedirs(directory)


if __name__ == '__main__':
    # Loading the data (converting each image into a tensor and normalizing between [-1, 1])
    transform = Compose([
        # torchvision.transforms.Resize(40),
        # torchvision.transforms.RandomResizedCrop(32, scale=(0.8, 1.0)),
        ToTensor(),
        torchvision.transforms.Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))
    ])

    ds = CIFAR100

    # Create train batch loader
    train_dataset = ds("./datasets", download=True, train=True, transform=transform)
    train_loader = DataLoader(train_dataset, params['batch_size'], shuffle=True)

    # Create test batch loader
    test_dataset = ds("./datasets", download=True, train=False, transform=transform)
    test_loader = DataLoader(test_dataset, params['batch_size'], shuffle=True)

    # Train iterable
    train_iterator = iter(cycle(train_loader))

    print(f'Size of training dataset: {len(train_loader.dataset)}')
    print(f'Size of testing dataset: {len(test_loader.dataset)}')

    # Initialise Models and apply weights
    netG = Generator(params['nc'], params['nz'], params['ngf']).to(device)
    netG.apply(weights_init)
    netD = Discriminator(params['nc'], params['ndf']).to(device)
    netD.apply(weights_init)

    # Loss functin
    criterion = nn.BCELoss().to(device)
    fixed_noise = torch.randn(params['batch_size'], params['nz'], 1, 1).to(device)

    # Initialise optimiser
    optimizerD = Adam(netD.parameters(), lr=params['lr'], betas=(params['beta1'], 0.999))
    optimizerG = Adam(netG.parameters(), lr=params['lr'], betas=(params['beta1'], 0.999))

    # Check how many parameters in total between 2 models
    total_params = len(torch.nn.utils.parameters_to_vector(netG.parameters())) + len(
        torch.nn.utils.parameters_to_vector(netD.parameters()))
    print(f'> Number of model parameters {total_params}')
    if total_params > 1000000:
        print("> Warning: you have gone over your parameter budget and will have a grade penalty!")


    # Lists to keep track of progress
    img_list = []
    G_losses = []
    D_losses = []
    iters = 0

    # Directory names for image storage
    n_samples = 10000
    real_images_dir = 'real_images'
    generated_images_dir = 'generated_images'

    print("Training:")

    # Training
    for epoch in range(params['n_epochs']):
        for i in range(1000):
            data, _ = next(train_iterator)
            #---------------------------
            # Update Discriminator Model
            #---------------------------

            # Train with real images
            netD.zero_grad()
            data = data.to(device)
            b_size = data.size(0)
            # Use one-sided label smoothing where real labels are filled with 0.9 instead of 1
            label = torch.full((b_size,), params['real_label'], dtype=torch.float, device=device)
            # Forward pass
            output = netD(data).view(-1)
            # Loss of real images
            errD_real = criterion(output, label)
            # Gradients
            errD_real.backward()

            # Train with fake images
            # Generate latent vectors with batch size indicated in params
            noise = torch.randn(b_size, params['nz'], 1, 1, device=device)
            fake = netG(noise)
            # One-sided label smoothing where fake labels are filled with 0
            label.fill_(params['fake_label'])
            # Classify fake images with Discriminator
            output = netD(fake.detach()).view(-1)
            # Discriminator's loss on the fake images
            errD_fake = criterion(output, label)
            # Gradients for backward pass
            errD_fake.backward()
            # Compute sum error of Discriminator
            errD = errD_real + errD_fake
            # Update Discriminator
            optimizerD.step()

            #-----------------------
            # Update Generator Model
            #-----------------------

            netG.zero_grad()
            label.fill_(params['real_label'])  # fake labels are real for generator cost
            # Forward pass of fake images through Discriminator
            output = netD(fake).view(-1)
            # G's loss based on this output
            errG = criterion(output, label)
            # Calculate gradients for Generator
            errG.backward()
            # Update Generator
            optimizerG.step()

            # Output training stats
            if (iters + 1) % 1000 == 0:
                print('[%d/%d]\tLoss_D: %.4f\tLoss_G: %.4f'
                      % (epoch + 1, params['n_epochs'], errD.item(), errG.item()))

            # Save Losses for plotting
            G_losses.append(errG.item())
            D_losses.append(errD.item())

            # Sample for visualisation
            if (epoch + 1 == params['n_epochs']) and (i == len(train_loader) - 1):
                with torch.no_grad():
                    fake = netG(fixed_noise).detach().cpu()
                img_list.append(vutils.make_grid(fake, padding=2, normalize=True))

            iters += 1

    # Sampling from latent space and save 10000 samples to dir
    with torch.no_grad():
        sample_noise = torch.randn(n_samples, params['nz'], 1, 1).to(device)
        fake = netG(sample_noise).detach().cpu()

    # now show some interpolations (note you do not have to do linear interpolations as shown here, you can do non-linear or gradient-based interpolation if you wish)
    col_size = int(np.sqrt(params['batch_size']))

    z0 = sample_noise[0:col_size].repeat(col_size, 1)  # z for top row
    z1 = sample_noise[params['batch_size'] - col_size:].repeat(col_size, 1)  # z for bottom row

    t = torch.linspace(0, 1, col_size).unsqueeze(1).repeat(1, col_size).view(params['batch_size'], 1).to(device)

    lerp_z = (1 - t) * z0 + t * z1  # linearly interpolate between two points in the latent space
    with torch.no_grad():
        lerp_g = netG(lerp_z)  # sample the model at the resulting interpolated latents

    plt.figure(figsize=(10, 5))
    plt.title('Interpolation')
    plt.rcParams['figure.dpi'] = 100
    plt.grid(False)
    plt.imshow(torchvision.utils.make_grid(lerp_g).cpu().numpy().transpose(1, 2, 0), cmap=plt.cm.binary)
    plt.savefig('Interpolation')

    setup_directory(generated_images_dir)

    for n, image in enumerate(fake):
        save_image(image, os.path.join(generated_images_dir, f"gen_img_{n}.png"))

    # Plot figures using matplotlib
    plt.figure(figsize=(10, 5))
    plt.title("Generator and Discriminator Loss During Training")
    plt.plot(G_losses, label="G")
    plt.plot(D_losses, label="D")
    plt.xlabel("iterations")
    plt.ylabel("Loss")
    plt.legend()
    plt.savefig('training_loss.png')

    plt.figure(figsize=(15, 15))
    plt.axis("off")
    plt.title("Fake Images")
    plt.imshow(np.transpose(img_list[-1], (1, 2, 0)))
    plt.savefig('gen_img.png')

    # compute FID
    score = fid.compute_fid(real_images_dir, generated_images_dir, mode="clean")
    print(f"FID score: {score}")
