
#include "kernel.h"
#include "grid.h"

using namespace std;
namespace Manta {

	KERNEL(bnd = 1)
	void ComputeDiv(FlagGrid& flags, Grid<Real>& div, MACGrid& vel){

	}

	KERNEL(bnd = 1)
	void iterate_p(const Grid<Real>& div, Grid<Real>& pressure, const Grid<Real> &A0, const Grid<Real> &A1) {

	}

	KERNEL(bnd = 1)
	void iterate_r(const Grid<Real>& div, Grid<Real>& pressure, Real &residual, const Grid<Real> &A0, const Grid<Real> &A1) {
			
	}

	KERNEL(bnd = 1)
	void iterate2(const Grid<Real>& div, Grid<Real>& pressure, Real &residual, const Grid<Real> &A0, const Grid<Real> &A1) {

	}

	KERNEL(bnd = 1)
	void UpdateVel(const FlagGrid& flags, MACGrid& vel, const Grid<Real>& pressure){

	}

	KERNEL()
	void ComputeA0(const FlagGrid& flags, Grid<Real> &A0) {

	}

	KERNEL(bnd = 1)
	void ComputeA1(const Grid<Real> &A0, Grid<Real> &A1) {

	}

	PYTHON() void solvePressureGS(FlagGrid& flags, MACGrid& vel, Grid<Real>& pressure, Real gsAccuracy = 1e-4) {

	}

	PYTHON() Real getMaxDivergence(MACGrid& vel, FlagGrid& flags){
		return 0;
	}

} // end namespace