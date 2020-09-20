# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/10-simclr.ipynb (unless otherwise specified).

__all__ = ['get_aug_pipe', 'create_encoder', 'MLP', 'SimCLRModel', 'create_simclr_model', 'remove_diag', 'SimCLRLoss',
           'SimCLR']

# Cell
from fastai.vision.all import *
import kornia

# Cell
def get_aug_pipe(size, stats=imagenet_stats, s=.6, color=True, xtra_tfms=[]):
    "SimCLR augmentations"
    tfms = []
    tfms += [kornia.augmentation.RandomResizedCrop((size, size), scale=(0.2, 1.0), ratio=(3/4, 4/3))]
    tfms += [kornia.augmentation.RandomHorizontalFlip()]

    if color: tfms += [kornia.augmentation.ColorJitter(0.8*s, 0.8*s, 0.8*s, 0.2*s)]
    if color: tfms += [kornia.augmentation.RandomGrayscale(p=0.2)]
    if stats is not None: tfms += [Normalize.from_stats(*stats)]

    tfms += xtra_tfms

    pipe = Pipeline(tfms)
    pipe.split_idx = 0
    return pipe

# Cell
def create_encoder(arch, n_in=3, pretrained=True, cut=None, concat_pool=True):
    "Create encoder from a given arch backbone"
    encoder = create_body(arch, n_in, pretrained, cut)
    pool = AdaptiveConcatPool2d() if concat_pool else nn.AdaptiveAvgPool2d(1)
    return nn.Sequential(*encoder, pool, Flatten())

# Cell
class MLP(Module):
    "MLP module as described in paper"
    def __init__(self, dim, projection_size=128, hidden_size=256):
        self.net = nn.Sequential(
            nn.Linear(dim, hidden_size),
            nn.ReLU(inplace=True),
            nn.Linear(hidden_size, projection_size)
        )

    def forward(self, x):
        return self.net(x)

# Cell
class SimCLRModel(Module):
    "Compute predictions of concatenated xi and xj"
    def __init__(self,encoder,projector): self.encoder,self.projector = encoder,projector
    def forward(self,x): return self.projector(self.encoder(x))

# Cell
def create_simclr_model(arch=resnet50, n_in=3, pretrained=True, cut=None, concat_pool=True,
                      hidden_size=256, projection_size=128):
    "Create SimCLR from a given arch"
    encoder = create_encoder(arch, n_in, pretrained, cut, concat_pool)
    with torch.no_grad(): representation = encoder(torch.randn((2,n_in,128,128)))
    projector = MLP(representation.size(1), projection_size, hidden_size=hidden_size)
    apply_init(projector)
    return SimCLRModel(encoder, projector)

# Cell
def remove_diag(x):
    bs = x.shape[0]
    return x[~torch.eye(bs).bool()].reshape(bs,bs-1)

# Cell
class SimCLRLoss(Module):
    def __init__(self, temp=0.1):
        self.temp = temp

    def forward(self, inp, targ):
        bs,feat = inp.shape
        csim = F.cosine_similarity(inp, inp.unsqueeze(dim=1), dim=-1)/self.temp
        csim = remove_diag(csim)
        targ = remove_diag(torch.eye(targ.shape[0], device=inp.device)[targ]).nonzero()[:,-1]
        return F.cross_entropy(csim, targ)

# Cell
class SimCLR(Callback):
    def __init__(self, size=256, **aug_kwargs):
        self.aug1 = get_aug_pipe(size, **aug_kwargs)
        self.aug2 = get_aug_pipe(size, **aug_kwargs)

    def before_batch(self):
        xi,xj = self.aug1(self.x), self.aug2(self.x)
        self.learn.xb = (torch.cat([xi, xj]),)
        bs = self.learn.xb[0].shape[0]
        self.learn.yb = (torch.arange(bs, device=self.dls.device).roll(bs//2),)

    def show_one(self):
        xb = TensorImage(self.learn.xb[0])
        bs = len(xb)//2
        i = np.random.choice(bs)
        xb = self.aug1.decode(xb.to('cpu').clone()).clamp(0,1)
        images = [xb[i], xb[bs+i]]
        show_images(images)