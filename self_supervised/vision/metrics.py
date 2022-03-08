# AUTOGENERATED! DO NOT EDIT! File to edit: nbs/70 - vision.metrics.ipynb (unless otherwise specified).

__all__ = ['KNNProxyMetric']

# Cell
from fastai.vision.all import *

# Cell
class KNNProxyMetric(Callback):
    "A metric which calculates knn-1 accuracy. Use with a labeled validation set."
    order,run_train,run_valid=8,False,True

    def before_batch(self):
        self.orig_x, self.orig_y = self.x, self.y

    def before_validate(self):
        self.embs = tensor([]).to(self.dls.device)
        self.targs = tensor([]).to(self.dls.device)

    def after_pred(self):
        self.embs = torch.cat([self.embs, self.model.encoder(self.orig_x)])
        self.targs = torch.cat([self.targs, self.orig_y])

    def accuracy(self):
        self.embs = F.normalize(self.embs)
        sim = self.embs @ self.embs.T
        nearest_neighbor = sim.argsort(dim=1, descending=True)[:,2]
        self.targs = TensorBase(self.targs)
        return (self.targs == self.targs[nearest_neighbor]).float().mean()

    def after_fit(self):
        del self.embs, self.targs
        torch.cuda.empty_cache()