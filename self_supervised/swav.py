# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/12-swav.ipynb (unless otherwise specified).

__all__ = ['SwAVModel', 'create_swav_model', 'sinkhorn_knopp', 'SWAVLoss', 'SWAV']

# Cell
from fastai.vision.all import *
from .augmentations import *
from .layers import *

# Cell
class SwAVModel(Module):
    "SwAV model"
    def __init__(self,encoder,projector,prototypes):
        self.encoder,self.projector,self.prototypes = encoder,projector,prototypes

    def forward(self, inputs):

        if not isinstance(inputs, list): inputs = [inputs]

        crop_idxs = torch.cumsum(torch.unique_consecutive(
                                torch.tensor([inp.shape[-1] for inp in inputs]),
                                return_counts=True)[1], 0)

        start_idx = 0
        for idx in crop_idxs:
            _z = self.encoder(torch.cat(inputs[start_idx: idx]))
            if not start_idx: z = _z
            else:             z = torch.cat((z, _z))
            start_idx = idx

        z = F.normalize(self.projector(z))
        return z, self.prototypes(z)

# Cell
def create_swav_model(encoder, n_in=3, hidden_size=256, projection_size=128, n_protos=3000):
    "Create SwAV model"
    with torch.no_grad(): representation = encoder(torch.randn((2,n_in,128,128)))
    projector = create_mlp_module(representation.size(1), hidden_size, projection_size, bn=True)
    prototypes = nn.Linear(projection_size, n_protos, bias=False)
    apply_init(projector)
    with torch.no_grad():
        w = prototypes.weight.data.clone()
        prototypes.weight.copy_(F.normalize(w))
    return SwAVModel(encoder, projector, prototypes)

# Cell
def sinkhorn_knopp(Q, nmb_iters, device=default_device):
    "https://en.wikipedia.org/wiki/Sinkhorn%27s_theorem#Sinkhorn-Knopp_algorithm"
    with torch.no_grad():
        sum_Q = torch.sum(Q)
        Q /= sum_Q

        r = (torch.ones(Q.shape[0]) / Q.shape[0]).to(device)
        c = (torch.ones(Q.shape[1]) / Q.shape[1]).to(device)

        curr_sum = torch.sum(Q, dim=1)

        for it in range(nmb_iters):
            u = curr_sum
            Q *= (r / u).unsqueeze(1)
            Q *= (c / torch.sum(Q, dim=0)).unsqueeze(0)
            curr_sum = torch.sum(Q, dim=1)
        return (Q / torch.sum(Q, dim=0, keepdim=True)).t().float()

# Cell
class SWAVLoss(Module):
    def forward(self,log_ps,qs):
        loss = 0
        t = (qs.unsqueeze(1)*log_ps.unsqueeze(0)).sum(-1).mean(-1)
        for i, ti in enumerate(t): loss-=(ti.sum() - ti[i])/(len(ti)-1)/len(t)
        return loss

# Cell
class SWAV(Callback):
    order,run_valid = 9,True
    def __init__(self, aug_func=get_batch_augs, print_augs=False,
                       crop_sizes=[224,96],
                       num_crops=[2,6],
                       min_scales=[0.25,0.05],
                       max_scales=[1.,0.14],
                       crop_assgn_ids=[0,1],
                       eps=0.05,
                       n_sinkh_iter=3,
                       temp=0.1,
                       **aug_kwargs):

        store_attr('num_crops,crop_assgn_ids,temp,eps,n_sinkh_iter')
        self.augs = []
        for nc, size, mins, maxs in zip(num_crops, crop_sizes, min_scales, max_scales):
            self.augs += [aug_func(size, resize_scale=(mins, maxs), **aug_kwargs) for i in range(nc)]
        if print_augs:
            for aug in self.augs: print(aug)

    def before_batch(self):
        "Compute multi crop inputs"
        self.bs = self.x.size(0)
        self.learn.xb = ([aug(self.x) for aug in self.augs],)


    def after_pred(self):
        "Compute ps and qs"
        embedding, output = self.pred
        with torch.no_grad():
            qs = []
            for i in self.crop_assgn_ids:
                # TODO: Store previous batch embeddings
                # to be used in Q calculation
                # Store approx num_proto//bs batches
                # output.size(1)//self.bs
                target_b = output[self.bs*i:self.bs*(i+1)]
                q = torch.exp(target_b/self.eps).t()
                q = sinkhorn_knopp(q, self.n_sinkh_iter, q.device)
                qs.append(q)

        log_ps = []
        for v in np.arange(np.sum(self.num_crops)):
            log_p = F.log_softmax(output[self.bs*v:self.bs*(v+1)] / self.temp, dim=1)
            log_ps.append(log_p)

        log_ps = torch.stack(log_ps)
        qs = torch.stack(qs)
        self.learn.pred, self.learn.yb = log_ps, (qs,)


    def after_batch(self):
        with torch.no_grad():
            w = self.learn.model.prototypes.weight.data.clone()
            self.learn.model.prototypes.weight.data.copy_(F.normalize(w))


    def show_one(self):
        xb = self.learn.xb[0]
        i = np.random.choice(self.bs)
        images = [aug.decode(b.to('cpu').clone()).clamp(0.1)[i]
                      for b, aug in zip(xb, self.augs)]
        show_images(images)