r"""4x AI upscaling of textures with ESRGAN-family models on the GPU (PyTorch, no other packages).

    python esrgan.py --model E:\tools\upscale\models\4x-UltraSharp.pth in.png out.png [in2.png out2.png ...]
    python esrgan.py --model ... --pairs list.txt          # lines "in<TAB>out"

Models (UPSCALE_MODELS, default E:\tools\upscale\models - the weights are not in the repo): 4x-UltraSharp.pth
(Kim2091, CC BY-NC-SA 4.0; the one export_model.py --upscale uses - it keeps the game's fabric grain and iris fibres),
RealESRGAN_x4plus.pth / RealESRGAN_x4plus_anime_6B.pth (xinntao, BSD-3; they paint flat, the anime one outlines dye-mask
edges).  Both checkpoint layouts of the RRDBNet load: Real-ESRGAN's (conv_first / body.N.rdbK / conv_up1 ...) and old
ESRGAN's (model.0 / model.1.sub.N.RDBK / model.3 ...).  Downloads: hf-mirror.com/lokCX/4x-Ultrasharp,
github.com/xinntao/Real-ESRGAN/releases (check the sha256).

RGB goes through the network in tiles (reflect-padded, fp16 on CUDA); an alpha channel is resized with Lanczos so
cut-outs and masks get no invented detail.  --max-side caps the output (Lanczos down from the 4x result).
"""
import argparse
import os
import sys
import time

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from PIL import Image

MODELS = os.environ.get('UPSCALE_MODELS', r'E:\tools\upscale\models')


class RDB(nn.Module):
    def __init__(self, nf, gc):
        super().__init__()
        self.conv1 = nn.Conv2d(nf, gc, 3, 1, 1)
        self.conv2 = nn.Conv2d(nf + gc, gc, 3, 1, 1)
        self.conv3 = nn.Conv2d(nf + 2 * gc, gc, 3, 1, 1)
        self.conv4 = nn.Conv2d(nf + 3 * gc, gc, 3, 1, 1)
        self.conv5 = nn.Conv2d(nf + 4 * gc, nf, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(0.2, inplace=True)

    def forward(self, x):
        x1 = self.lrelu(self.conv1(x))
        x2 = self.lrelu(self.conv2(torch.cat((x, x1), 1)))
        x3 = self.lrelu(self.conv3(torch.cat((x, x1, x2), 1)))
        x4 = self.lrelu(self.conv4(torch.cat((x, x1, x2, x3), 1)))
        return self.conv5(torch.cat((x, x1, x2, x3, x4), 1)) * 0.2 + x


class RRDB(nn.Module):
    def __init__(self, nf, gc):
        super().__init__()
        self.rdb1, self.rdb2, self.rdb3 = RDB(nf, gc), RDB(nf, gc), RDB(nf, gc)

    def forward(self, x):
        return self.rdb3(self.rdb2(self.rdb1(x))) * 0.2 + x


class RRDBNet(nn.Module):
    """ESRGAN generator, 4x (two nearest-neighbour 2x steps)."""
    def __init__(self, nb, nf=64, gc=32, in_ch=3, out_ch=3):
        super().__init__()
        self.conv_first = nn.Conv2d(in_ch, nf, 3, 1, 1)
        self.body = nn.Sequential(*[RRDB(nf, gc) for _ in range(nb)])
        self.conv_body = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_up1 = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_up2 = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_hr = nn.Conv2d(nf, nf, 3, 1, 1)
        self.conv_last = nn.Conv2d(nf, out_ch, 3, 1, 1)
        self.lrelu = nn.LeakyReLU(0.2, inplace=True)

    def forward(self, x):
        feat = self.conv_first(x)
        feat = feat + self.conv_body(self.body(feat))
        feat = self.lrelu(self.conv_up1(F.interpolate(feat, scale_factor=2, mode='nearest')))
        feat = self.lrelu(self.conv_up2(F.interpolate(feat, scale_factor=2, mode='nearest')))
        return self.conv_last(self.lrelu(self.conv_hr(feat)))


OLD_NAMES = {'model.0': 'conv_first', 'model.3': 'conv_up1', 'model.6': 'conv_up2', 'model.8': 'conv_hr',
             'model.10': 'conv_last'}


def _from_old(sd):
    """old ESRGAN keys (model.1.sub.N.RDBk.convj.0.weight ...) -> RRDBNet names"""
    nb = 1 + max(int(k.split('.')[3]) for k in sd if k.startswith('model.1.sub.') and '.RDB' in k)
    out = {}
    for k, v in sd.items():
        p = k.split('.')
        if k.startswith('model.1.sub.'):
            if int(p[3]) == nb:                                  # model.1.sub.<nb>.weight = the trunk conv
                out['conv_body.' + p[4]] = v
            else:
                out['body.%s.%s.%s.%s' % (p[3], p[4].lower(), p[5], p[7])] = v
        else:
            out[OLD_NAMES['.'.join(p[:2])] + '.' + p[2]] = v
    return out


def load_model(path, device=None, half=True):
    ck = torch.load(path, map_location='cpu', weights_only=True)
    sd = ck.get('params_ema') or ck.get('params') or ck if isinstance(ck, dict) else ck
    if 'model.0.weight' in sd:
        sd = _from_old(sd)
    nb = len({k.split('.')[1] for k in sd if k.startswith('body.')})
    nf, in_ch = sd['conv_first.weight'].shape[:2]
    gc = sd['body.0.rdb1.conv1.weight'].shape[0]
    if in_ch != 3:
        raise SystemExit('%s: only plain 4x RRDBNet models (3 input channels), this one has %d' % (path, in_ch))
    net = RRDBNet(nb, nf, gc)
    net.load_state_dict(sd, strict=True)
    device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
    net = net.eval().to(device)
    if half and device == 'cuda':
        net = net.half()
    return net


@torch.inference_mode()
def upscale_rgb(net, rgb, tile=512, pad=16):
    """HxWx3 float [0,1] -> 4Hx4Wx3"""
    p = next(net.parameters())
    h, w = rgb.shape[:2]
    x = torch.from_numpy(np.ascontiguousarray(rgb.transpose(2, 0, 1)))[None].to(p.device, p.dtype)
    x = F.pad(x, (pad, pad, pad, pad), mode='reflect')
    H, W = x.shape[2:]
    out = torch.empty((1, 3, H * 4, W * 4), dtype=p.dtype, device=p.device)
    for y0 in range(0, H, tile):
        for x0 in range(0, W, tile):
            y1, x1 = min(y0 + tile, H), min(x0 + tile, W)
            ya, xa, yb, xb = max(y0 - pad, 0), max(x0 - pad, 0), min(y1 + pad, H), min(x1 + pad, W)
            o = net(x[:, :, ya:yb, xa:xb])
            out[:, :, y0 * 4:y1 * 4, x0 * 4:x1 * 4] = o[:, :, (y0 - ya) * 4:(y1 - ya) * 4, (x0 - xa) * 4:(x1 - xa) * 4]
    out = out[:, :, pad * 4:(pad + h) * 4, pad * 4:(pad + w) * 4]
    return out.float().clamp_(0, 1)[0].permute(1, 2, 0).cpu().numpy()


def upscale_file(net, src, dst, max_side=4096):
    im = Image.open(src)
    has_alpha = im.mode in ('RGBA', 'LA', 'PA') or 'transparency' in im.info
    rgba = im.convert('RGBA')
    rgb = np.asarray(rgba)[..., :3].astype(np.float32) / 255.0
    out = Image.fromarray((upscale_rgb(net, rgb) * 255.0 + 0.5).astype(np.uint8), 'RGB')
    if has_alpha:
        out.putalpha(rgba.getchannel('A').resize(out.size, Image.LANCZOS))
    if max(out.size) > max_side:
        f = max_side / max(out.size)
        out = out.resize((round(out.size[0] * f), round(out.size[1] * f)), Image.LANCZOS)
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    out.save(dst, compress_level=6)
    return im.size, out.size


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--model', default=os.path.join(MODELS, '4x-UltraSharp.pth'))
    ap.add_argument('--pairs', help='text file, one "in<TAB>out" per line')
    ap.add_argument('--max-side', type=int, default=4096)
    ap.add_argument('files', nargs='*', help='in out [in out ...]')
    a = ap.parse_args()
    pairs = list(zip(a.files[::2], a.files[1::2]))
    if a.pairs:
        pairs += [tuple(l.rstrip('\n').split('\t')) for l in open(a.pairs, encoding='utf-8') if l.strip()]
    if not pairs:
        ap.print_help()
        return
    t0 = time.time()
    net = load_model(a.model)
    print('model %s on %s (%.1fs)' % (os.path.basename(a.model), next(net.parameters()).device, time.time() - t0), flush=True)
    for src, dst in pairs:
        t = time.time()
        s0, s1 = upscale_file(net, src, dst, a.max_side)
        print('  %-48s %4dx%-4d -> %4dx%-4d  %.1fs' % (os.path.basename(src), s0[0], s0[1], s1[0], s1[1], time.time() - t), flush=True)
    print('done %d files in %.0fs' % (len(pairs), time.time() - t0))


if __name__ == '__main__':
    sys.exit(main())
