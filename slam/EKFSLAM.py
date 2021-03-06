from os import error
from typing import Tuple
import numpy as np
from numpy import ndarray
from dataclasses import dataclass, field
from scipy.linalg import block_diag
import scipy.linalg as la
from utils import rotmat2d
from JCBB import JCBB
import utils
import solution


@dataclass
class EKFSLAM:
    Q: ndarray
    R: ndarray
    do_asso: bool
    alphas: 'ndarray[2]' = field(default=np.array([0.001, 0.0001]))
    sensor_offset: 'ndarray[2]' = field(default=np.zeros(2))

    def f(self, x: np.ndarray, u: np.ndarray) -> np.ndarray:
        """Add the odometry u to the robot state x.

        Parameters
        ----------
        x : np.ndarray, shape=(3,)
            the robot state
        u : np.ndarray, shape=(3,)
            the odometry

        Returns
        -------
        np.ndarray, shape = (3,)
            the predicted state
        """
        # TODO replace this with your own code

        x_k = x[0] + u[0] * np.cos(x[2]) - u[1]*np.sin(x[2])
        y_k = x[1] + u[0] * np.sin(x[2]) + u[1]*np.cos(x[2])
        phi_k = x[2] + u[2]

        xpred = np.array([x_k, y_k, phi_k])
        #xpred = solution.EKFSLAM.EKFSLAM.f(self, x, u)

        # TODO, eq (11.7). Should wrap heading angle between (-pi, pi), see utils.wrapToPi
        xpred[2] = utils.wrapToPi(xpred[2])

        return xpred
        

    def Fx(self, x: np.ndarray, u: np.ndarray) -> np.ndarray:
        """Calculate the Jacobian of f with respect to x.

        Parameters
        ----------
        x : np.ndarray, shape=(3,)
            the robot state
        u : np.ndarray, shape=(3,)
            the odometry

        Returns
        -------
        np.ndarray
            The Jacobian of f wrt. x.
        """
        # TODO replace this with your own code
        Fx = np.identity(3)
        Fx[0,2] = -u[0]*np.sin(x[2])-u[1]*np.cos(x[2])
        Fx[1,2] = u[0]*np.cos(x[2])-u[1]*np.sin(x[2])
        

        #Fx = solution.EKFSLAM.EKFSLAM.Fx(self, x, u)

        return Fx

    def Fu(self, x: np.ndarray, u: np.ndarray) -> np.ndarray:
        """Calculate the Jacobian of f with respect to u.

        Parameters
        ----------
        x : np.ndarray, shape=(3,)
            the robot state
        u : np.ndarray, shape=(3,)
            the odometry

        Returns
        -------
        np.ndarray
            The Jacobian of f wrt. u.
        """
        # TODO replace this with your own code
        #Fu = solution.EKFSLAM.EKFSLAM.Fu(self, x, u)

        Fu = np.array([
            [np.cos(x[2]),   -np.sin(x[2]), 0],
            [np.sin(x[2]),   np.cos(x[2]),  0],
            [0,              0,             1]])
        

        return Fu

    def predict(
        self, eta: np.ndarray, P: np.ndarray, z_odo: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Predict the robot state using the zOdo as odometry the corresponding state&map covariance.
        
        Parameters
        ----------
        eta : np.ndarray, shape=(3 + 2*#landmarks,)
            the robot state and map concatenated
        P : np.ndarray, shape=(3 + 2*#landmarks,)*2
            the covariance of eta
        z_odo : np.ndarray, shape=(3,)
            the measured odometry

        Returns
        -------
        Tuple[np.ndarray, np.ndarray], shapes= (3 + 2*#landmarks,), (3 + 2*#landmarks,)*2
            predicted mean and covariance of eta.
        """

        # check inout matrix
        assert np.allclose(P, P.T), "EKFSLAM.predict: not symmetric P input"
        assert np.all(
            np.linalg.eigvals(P) >= 0
        ), "EKFSLAM.predict: non-positive eigen values in P input"
        assert (
            eta.shape * 2 == P.shape
        ), "EKFSLAM.predict: input eta and P shape do not match"
        etapred = np.empty_like(eta)

        x = eta[:3]
        etapred[:3] = self.f(x, z_odo)  # TODO robot state prediction
        etapred[3:] =eta[3:]  # TODO landmarks: no effect

        Fx = self.Fx(x, z_odo)  # TODO
        Fu = self.Fu(x, z_odo)  # TODO

        # evaluate covariance prediction in place to save computation
        # only robot state changes, so only rows and colums of robot state needs changing
        # cov matrix layout:
        # [[P_xx, P_xm],
        # [P_mx, P_mm]]
        
        if np.shape(P[0])[0] > 3:
            G = np.vstack([np.identity(3), np.zeros([(np.shape(P[0])[0]-3), 3])])
        else:
            G = np.identity(3)

        Q =  Fu @ self.Q @ Fu.T

        F = Fx
        # TODO robot cov prediction
        # TODO robot-map covariance prediction
        # TODO map-robot covariance: transpose of the above
        if np.shape(P[0])[0] > 3:
            F = np.identity(np.shape(P[0])[0])
            F[:3, :3] = Fx

            #P[:3, 3:] = F @ P[:3, 3:] @ F.T #+ G @ self.Q @ G.T  
            #P[3:, :3] = F @ P[3:, :3] @ F.T #+ G @ self.Q @ G.T  
        P= F @ P @ F.T + G @ Q @ G.T

        #etapred_old, P = solution.EKFSLAM.EKFSLAM.predict(self, eta, P, z_odo)

        assert np.allclose(P, P.T), "EKFSLAM.predict: not symmetric P"
        assert np.all(
            np.linalg.eigvals(P) > 0
        ), "EKFSLAM.predict: non-positive eigen values"
        assert (
            etapred.shape * 2 == P.shape
        ), "EKFSLAM.predict: calculated shapes does not match"


        return etapred, P



    def h(self, eta: np.ndarray) -> np.ndarray:
        """Predict all the landmark positions in sensor frame.

        Parameters
        ----------
        eta : np.ndarray, shape=(3 + 2 * #landmarks,)
            The robot state and landmarks stacked.

        Returns
        -------
        np.ndarray, shape=(2 * #landmarks,)
            The landmarks in the sensor frame.
        """


        # extract states and map
        x = eta[0:3]
        # reshape map (2, #landmarks), m[:, j] is the jth landmark
        m = eta[3:].reshape((-1, 2)).T

        Rot = rotmat2d(-x[2])
        Rot_pos = rotmat2d(x[2])

        # None as index ads an axis with size 1 at that position.
        # Numpy broadcasts size 1 dimensions to any size when needed
        #delta_m = np.zeros_like(m)
        zpred_r = np.zeros_like(m[0]) 
        zpred_theta = np.zeros_like(m[0])
        L_off = Rot_pos @ self.sensor_offset

        for i in range(np.size(m[1])):
            delta_m = m[:,i]-x[0:2]- L_off  # TODO, relative position of landmark to sensor on robot in world frame
                        
            zpredcart = Rot @ delta_m # TODO, predicted measurements in cartesian coordinates, beware sensor offset for VP
            zpred_r[i] = np.linalg.norm(zpredcart[0:2], 2)  # TODO, ranges
            zpred_theta[i] = np.arctan2(zpredcart[1], zpredcart[0])  # TODO, bearings

        #print(" delta_m" , delta_m)
        #print(" zpred_r" , zpred_r)
        #  print(" zpred_theta" ,zpred_theta )
        zpred = np.vstack([zpred_r, zpred_theta])  # TODO, the two arrays above stacked on top of each other vertically like
        # [ranges;
        #  bearings]
        # into shape (2, #lmrk)

        # stack measurements along one dimension, [range1 bearing1 range2 bearing2 ...]
        zpred = zpred.T.ravel()

        assert (
            zpred.ndim == 1 and zpred.shape[0] == eta.shape[0] - 3
        ), "SLAM.h: Wrong shape on zpred"
        
        #zpred = solution.EKFSLAM.EKFSLAM.h(self, eta)

        return zpred

    def h_jac(self, eta: np.ndarray) -> np.ndarray:
        """Calculate the jacobian of h.

        Parameters
        ----------
        eta : np.ndarray, shape=(3 + 2 * #landmarks,)
            The robot state and landmarks stacked.

        Returns
        -------
        np.ndarray, shape=(2 * #landmarks, 3 + 2 * #landmarks)
            the jacobian of h wrt. eta.
        """
        

        # extract states and map
        x = eta[0:3]
        # reshape map (2, #landmarks), m[j] is the jth landmark
        m = eta[3:].reshape((-1, 2)).T

        numM = m.shape[1]

        Rot = rotmat2d(x[2])
        L_off = Rot @ self.sensor_offset
        delta_m = np.empty_like(m)
        # TODO, relative position of landmark to robot in world frame. m - rho that appears in (11.15) and (11.16)
        for i in range(np.size(m[1])):
            delta_m[:,i] = m[:,i]-x[0:2]
        

        # TODO, (2, #measurements), each measured position in cartesian coordinates like
        zc = np.empty_like(m)
        for i in range(np.size(m[1])):
            zc[:,i] = m[:,i]-x[0:2]- L_off
            

        # [x coordinates;
        #  y coordinates]

        zpred = self.h(eta) # TODO (2, #measurements), predicted measurements, like
        # [ranges;
        #  bearings]
        
        # TODO, ranges
        zr = np.array([])
        for i in range(int(np.size(zpred)/2)):
            zr = np.append(zr, zpred[i*2])

        Rpihalf = rotmat2d(np.pi / 2)

        # In what follows you can be clever and avoid making this for all the landmarks you _know_
        # you will not detect (the maximum range should be available from the data).
        # But keep it simple to begin with.

        # Allocate H and set submatrices as memory views into H
        # You may or may not want to do this like this
        # TODO, see eq (11.15), (11.16), (11.17)
        H = np.zeros((2 * numM, 3 + 2 * numM))
        Hx = H[:, :3]  # slice view, setting elements of Hx will set H as well
        Hm = H[:, 3:]  # slice view, setting elements of Hm will set H as well

        # proposed way is to go through landmarks one by one
        # preallocate and update this for some speed gain if looping
        jac_z_cb = -np.eye(2, 3)
        
        #print(hm_1)
        for i in range(numM):  # But this whole loop can be vectorized
            ind = 2 * i  # starting postion of the ith landmark into H
            # the inds slice for the ith landmark into H
            inds = slice(ind, ind + 2)

            delta_m_i = np.array([delta_m[0][i], delta_m[1][i]]).T
            #print("mi", delta_m_i)

            r_elem = -Rpihalf @ delta_m_i
            #print("r_elem", r_elem)
            jac_z_cb[0,2]  = r_elem[0]
            jac_z_cb[1,2] = r_elem[1]
            #print(zc)
            #print("zr", zr)
            zc_elem = np.array([zc[0][i],zc[1][i]]).T
            
            hx_1 = (zc_elem * (1/zr[i])) @ jac_z_cb

            hx_2 = ((zc_elem @ Rpihalf.T ) / (zr[i]**2)) @ jac_z_cb     
            
            hm_1 =  (zc_elem.T / (zr[i]))
            
            hm_2 = (zc_elem.T @ Rpihalf.T) / (zr[i]**2)
            
            Hx[ind] = hx_1
            Hx[ind+1] = hx_2
            Hm[ind][ind:(2+ind)] = hm_1
            Hm[ind+1][ind:(2+ind)] = hm_2







            # TODO: Set H or Hx and Hm here

        # TODO: You can set some assertions here to make sure that some of the structure in H is correct
        
        #H = solution.EKFSLAM.EKFSLAM.h_jac(self, eta)
        #print(H)
        return H

    def add_landmarks(
        self, eta: np.ndarray, P: np.ndarray, z: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Calculate new landmarks, their covariances and add them to the state.

        Parameters
        ----------
        eta : np.ndarray, shape=(3 + 2*#landmarks,)
            the robot state and map concatenated
        P : np.ndarray, shape=(3 + 2*#landmarks,)*2
            the covariance of eta
        z : np.ndarray, shape(2 * #newlandmarks,)
            A set of measurements to create landmarks for

        Returns
        -------
        Tuple[np.ndarray, np.ndarray], shapes=(3 + 2*(#landmarks + #newlandmarks,), (3 + 2*(#landmarks + #newlandmarks,)*2
            eta with new landmarks appended, and its covariance
        """
        # TODO replace this with your own code
        
        

        n = P.shape[0]
        assert z.ndim == 1, "SLAM.add_landmarks: z must be a 1d array"

        numLmk = z.shape[0] // 2
        
        lmnew = np.empty_like(z)

        Gx = np.empty((numLmk * 2, 3))
        Rall = np.zeros((numLmk * 2, numLmk * 2))

        I2 = np.eye(2)  # Preallocate, used for Gx
        # For transforming landmark position into world frame
        sensor_offset_world = rotmat2d(eta[2]) @ self.sensor_offset
        sensor_offset_world_der = rotmat2d(
            eta[2] + np.pi / 2) @ self.sensor_offset  # Used in Gx

        

        for j in range(numLmk):
            ind = 2 * j
            inds = slice(ind, ind + 2)
            zj = z[inds]           
            rot = rotmat2d(zj[1] + eta[2])  # TODO, rotmat in Gz     
            # TODO, calculate position of new landmark in world frame
            lmnew[inds] = eta[:2]+zj[0] * rot[:,0]+ sensor_offset_world
            Gx[inds, :2] = I2  # TODO
            #trig = np.array([[-np.sin(zj[1]+eta[2])],[np.cos(zj[1]+eta[2])]])
            Gx[inds, 2] = zj[0] * rot[:,1] + sensor_offset_world_der# TODO
            Gz = rot @ np.diag([1, zj[0]])  # TODO
            # TODO, Gz * R * Gz^T, transform measurement covariance from polar to cartesian coordinates
            Rall[inds, inds] = Gz @ self.R @ Gz.T

        
        
        assert len(lmnew) % 2 == 0, "SLAM.add_landmark: lmnew not even length"
        etaadded = np.block([eta, lmnew])  # TODO, append new landmarks to state vector
        
        # TODO, block diagonal of P_new, see problem text in 1g) in graded assignment 3
    
        
        top_left = P         # TODO, top left corner of P_new
        
        top_right = P[:,:3] @ Gx.T # TODO, top right corner of P_new
        
        # TODO, transpose of above. Should yield the same as calcualion, but this enforces symmetry and should be cheaper
        bottom_left = top_right.T
        
        
        bottom_right = Gx @ P[:3,:3] @ Gx.T + Rall
        
        Padded = np.block([[top_left, top_right],
                    [bottom_left, bottom_right]])

        assert (
            etaadded.shape * 2 == Padded.shape
        ), "EKFSLAM.add_landmarks: calculated eta and P has wrong shape"
        assert np.allclose(
            Padded, Padded.T
        ), "EKFSLAM.add_landmarks: Padded not symmetric"
        assert np.all(
            np.linalg.eigvals(Padded) >= 0
        ), "EKFSLAM.add_landmarks: Padded not PSD"

        

        return etaadded, Padded

    def associate(
        self, z: np.ndarray, zpred: np.ndarray, H: np.ndarray, S: np.ndarray,
    ):  # -> Tuple[*((np.ndarray,) * 5)]:
        """Associate landmarks and measurements, and extract correct matrices for these.

        Parameters
        ----------
        z : np.ndarray,
            The measurements all in one vector
        zpred : np.ndarray
            Predicted measurements in one vector
        H : np.ndarray
            The measurement Jacobian matrix related to zpred
        S : np.ndarray
            The innovation covariance related to zpred

        Returns
        -------
        Tuple[*((np.ndarray,) * 5)]
            The extracted measurements, the corresponding zpred, H, S and the associations.

        Note
        ----
        See the associations are calculated  using JCBB. See this function for documentation
        of the returned association and the association procedure.
        """
        if self.do_asso:
            # Associate
            a = JCBB(z, zpred, S, self.alphas[0], self.alphas[1])

            # Extract associated measurements
            zinds = np.empty_like(z, dtype=bool)
            zinds[::2] = a > -1  # -1 means no association
            zinds[1::2] = zinds[::2]
            zass = z[zinds]

            # extract and rearange predicted measurements and cov
            zbarinds = np.empty_like(zass, dtype=int)
            zbarinds[::2] = 2 * a[a > -1]
            zbarinds[1::2] = 2 * a[a > -1] + 1

            zpredass = zpred[zbarinds]
            Sass = S[zbarinds][:, zbarinds]
            Hass = H[zbarinds]

            assert zpredass.shape == zass.shape
            assert Sass.shape == zpredass.shape * 2
            assert Hass.shape[0] == zpredass.shape[0]

            return zass, zpredass, Hass, Sass, a
        else:
            # should one do something her
            pass

    def update(
        self, eta: np.ndarray, P: np.ndarray, z: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray, float, np.ndarray]:
        """Update eta and P with z, associating landmarks and adding new ones.

        Parameters
        ----------
        eta : np.ndarray
            [description]
        P : np.ndarray
            [description]
        z : np.ndarray, shape=(#detections, 2)
            [description]

        Returns
        -------
        Tuple[np.ndarray, np.ndarray, float, np.ndarray]
            [description]
        """
        # TODO replace this with your own code
        
        numLmk = (eta.size - 3) // 2
        assert (len(eta) - 3) % 2 == 0, "EKFSLAM.update: landmark lenght not even"
        
        #etaupd_old, Pupd_old, NIS_old, a_old = solution.EKFSLAM.EKFSLAM.update(self, eta, P, z)
        
        if numLmk > 0:
            # Prediction and innovation covariance
            zpred = self.h(eta)  # TODO
            H = self.h_jac(eta)  # TODO
            #etapred, Ppred = self.predict(eta, P, z)
            etapred = eta
            Ppred = P
            # Here you can use simply np.kron (a bit slow) to form the big (very big in VP after a while) R,
            # or be smart with indexing and broadcasting (3d indexing into 2d mat) realizing you are adding the same R on all diagonals
            gauss_r = self.R[0,0]
            gauss_theta = self.R[1,1]

            k_size = np.shape(H)[0]
            K_prod = np.zeros([k_size,k_size])

            for i in range(int(k_size/2)):
                K_prod[i*2,i*2] = gauss_r
                K_prod[(i*2)+1, (i*2)+1] = gauss_theta
                                
            S = H @ Ppred @ H.T + K_prod  # TODO
            #print("S", S)
            assert (
                S.shape == zpred.shape * 2
            ), "EKFSLAM.update: wrong shape on either S or zpred"
            z = z.ravel()  # 2D -> flat

            # Perform data association
            za, zpred, Ha, Sa, a = self.associate(z, zpred, H, S)

            # No association could be made, so skip update
            if za.shape[0] == 0:
                etaupd = eta
                Pupd = P
                NIS = 1  # TODO: beware this one when analysing consistency.
            else:
                # Create the associated innovation
                v = za.ravel() - zpred  # za: 2D -> flat
                v[1::2] = utils.wrapToPi(v[1::2])

                # Kalman mean update
                S_cho_factors = la.cho_factor(Sa) # Optional, used in places for S^-1, see scipy.linalg.cho_factor and scipy.linalg.cho_solve
                s_cho = la.cho_solve(S_cho_factors, np.eye(np.shape(Sa)[0]))

                W = Ppred @ Ha.T @ s_cho  # TODO, Kalman gain, can use S_cho_factors
                etaupd = etapred + W @ v  # TODO, Kalman update

                # Kalman cov update: use Joseph form for stability
                jo = -W @ Ha
                # same as adding Identity mat (np.identity(np.shape(Ppred)[0]) - W @ Ha)
                jo[np.diag_indices(jo.shape[0])] += 1
                Pupd = jo @ Ppred # TODO, Kalman update. This is the main workload on VP after speedups
                # calculate NIS, can use S_cho_factors
                NIS = v.T @ s_cho @ v  # TODO

                # When tested, remove for speed
                #for i in range(np.shape(Pupd)[0]):
                    #print("Pupd", Pupd[i])
                    #print("PupdT", Pupd.T[i])

                assert np.allclose(
                    Pupd, Pupd.T), "EKFSLAM.update: Pupd not symmetric"
                assert np.all(
                    np.linalg.eigvals(Pupd) > 0
                ), "EKFSLAM.update: Pupd not positive definite"

        else:  # All measurements are new landmarks,
            a = np.full(z.shape[0], -1)
            z = z.flatten()
            NIS = 1  # TODO: beware this one when analysing consistency.
            etaupd = eta
            Pupd = P

        # Create new landmarks if any is available
        if self.do_asso:
            is_new_lmk = a == -1
            if np.any(is_new_lmk):
                z_new_inds = np.empty_like(z, dtype=bool)
                z_new_inds[::2] = is_new_lmk
                z_new_inds[1::2] = is_new_lmk
                z_new = z[z_new_inds]
                
                etaupd, Pupd = self.add_landmarks(etaupd, Pupd, z_new)  # TODO, add new landmarks.

        assert np.allclose(
            Pupd, Pupd.T), "EKFSLAM.update: Pupd must be symmetric"
        assert np.all(np.linalg.eigvals(Pupd) >=
                      0), "EKFSLAM.update: Pupd must be PSD"
        
        '''
        for i in range(np.shape(etaupd)[0]):
                    print("etaupd", etaupd[i])
                    print("etaupd_old", etaupd_old[i])
        for i in range(np.shape(Pupd)[0]):
                    print("Pupd", Pupd[i])
                    print("Pupdold", Pupd_old[i])
       '''
        
        
        return etaupd, Pupd, NIS, a

    @classmethod
    def NEESes(cls, x: np.ndarray, P: np.ndarray, x_gt: np.ndarray,) -> np.ndarray:
        """Calculates the total NEES and the NEES for the substates
        Args:
            x (np.ndarray): The estimate
            P (np.ndarray): The state covariance
            x_gt (np.ndarray): The ground truth
        Raises:
            AssertionError: If any input is of the wrong shape, and if debug mode is on, certain numeric properties
        Returns:
            np.ndarray: NEES for [all, position, heading], shape (3,)
        """

        assert x.shape == (3,), f"EKFSLAM.NEES: x shape incorrect {x.shape}"
        assert P.shape == (3, 3), f"EKFSLAM.NEES: P shape incorrect {P.shape}"
        assert x_gt.shape == (
            3,), f"EKFSLAM.NEES: x_gt shape incorrect {x_gt.shape}"

        d_x = x - x_gt
        d_x[2] = utils.wrapToPi(d_x[2])
        assert (
            -np.pi <= d_x[2] <= np.pi
        ), "EKFSLAM.NEES: error heading must be between (-pi, pi)"

        d_p = d_x[0:2]
        P_p = P[0:2, 0:2]
        assert d_p.shape == (2,), "EKFSLAM.NEES: d_p must be 2 long"
        d_heading = d_x[2]  # Note: scalar
        assert np.ndim(
            d_heading) == 0, "EKFSLAM.NEES: d_heading must be scalar"
        P_heading = P[2, 2]  # Note: scalar
        assert np.ndim(
            P_heading) == 0, "EKFSLAM.NEES: P_heading must be scalar"

        # NB: Needs to handle both vectors and scalars! Additionally, must handle division by zero
        NEES_all = d_x @ (np.linalg.solve(P, d_x))
        NEES_pos = d_p @ (np.linalg.solve(P_p, d_p))
        try:
            NEES_heading = d_heading ** 2 / P_heading
        except ZeroDivisionError:
            NEES_heading = 1.0  # TODO: beware

        NEESes = np.array([NEES_all, NEES_pos, NEES_heading])
        NEESes[np.isnan(NEESes)] = 1.0  # We may divide by zero, # TODO: beware

        assert np.all(NEESes >= 0), "ESKF.NEES: one or more negative NEESes"
        return NEESes
