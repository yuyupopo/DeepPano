import torch
import torch.nn as nn
import torch.nn.functional as F

def conv3(in_channel, out_channel):
    return nn.Conv2d(in_channel, out_channel, kernel_size=3, padding=1)

class ConvBlock(nn.Module):
    """
    ( 3x3 conv -> batch norm -> elu ) x 2
    """
    def __init__(self, in_channel, out_channel):
        super(ConvBlock, self).__init__()
        self.layer = nn.Sequential(
            conv3(in_channel, out_channel),
            nn.BatchNorm2d(out_channel),
            nn.ELU(inplace=True),
            conv3(out_channel, out_channel),
            nn.BatchNorm2d(out_channel),
            nn.ELU(inplace=True)
        )
    
    def forward(self, x):
        x = self.layer(x)
        return x

class InBlock(nn.Module):
    def __init__(self, in_channel, out_channel):
        super(InBlock, self).__init__()
        self.layer = ConvBlock(in_channel, out_channel)
    
    def forward(self, x):
        x = self.layer(x)
        return x

class OutBlock(nn.Module):
    def __init__(self, in_channel, out_channel):
        super(OutBlock, self).__init__()
        self.layer = ConvBlock(in_channel, out_channel)
    
    def forward(self, x):
        x = self.layer(x)
        return x

class DownBlock(nn.Module):
    def __init__(self, in_channel, out_channel):
        super(DownBlock, self).__init__()
        self.down = nn.MaxPool2d(2)
        self.layer = ConvBlock(in_channel, out_channel)
    def forward(self, x):
        x = self.down(x)
        x = self.layer(x)
        return x

class UpBlock(nn.Module):
    def __init__(self, in_channel, out_channel, bilinear=True):
        super(UpBlock, self).__init__()
        self.up = nn.Upsample(scale_factor=2, mode='bilinear') if bilinear \
                        else nn.ConvTranspose2d(in_channel, out_channel, kernel_size=2, stride=2)

        self.layer = ConvBlock(in_channel, out_channel)

    def forward(self, x, prev):
        x = self.up(x)
        diffX = x.size()[2] - prev.size()[2]
        diffY = x.size()[3] - prev.size()[3]
        prev = F.pad(prev, (diffX // 2, int(diffX / 2),
                           diffY // 2, int(diffY / 2)))
        x = torch.cat([x, prev], dim=1)
        x = self.layer(x)
        return x


class UNet(nn.Module):
    def __init__(self, channels, classes, bilinear=True):
        super(UNet, self).__init__()
        self.in_conv = InBlock(channels, 8)
        self.down1 = DownBlock(8, 16)
        self.down2 = DownBlock(16, 32)
        self.down3 = DownBlock(32, 64)
        self.down4 = DownBlock(64, 64)
        self.up1 = UpBlock(128, 32, bilinear)
        self.up2 = UpBlock(64, 16, bilinear)
        self.up3 = UpBlock(32, 8, bilinear)
        self.up4 = UpBlock(16, 8, bilinear)
        self.out_conv = OutBlock(8, classes)

    def forward(self, x):
        x1 = self.in_conv(x)
        x2 = self.down1(x1)
        x3 = self.down2(x2)
        x4 = self.down3(x3)
        x5 = self.down4(x4)
        x = self.up1(x5, x4)
        x = self.up2(x, x3)
        x = self.up3(x, x2)
        x = self.up4(x, x1)
        x = self.out_conv(x)
        return x