import { lazy, Suspense } from 'react'
import { createBrowserRouter, Navigate, Outlet, RouterProvider } from 'react-router-dom'

import { ErrorPage } from './components/ErrorPage'
import { Layout } from './components/Layout'
import { Loading } from './components/ui'
import { PlantProvider } from './components/PlantProvider'

const Overview = lazy(() => import('./pages/Overview'))
const Twin = lazy(() => import('./pages/Twin'))
const Savings = lazy(() => import('./pages/Savings'))
const WhatIf = lazy(() => import('./pages/WhatIf'))
const Assistant = lazy(() => import('./pages/Assistant'))
const Documents = lazy(() => import('./pages/Documents'))
const Accuracy = lazy(() => import('./pages/Accuracy'))
const Designer = lazy(() => import('./pages/Designer'))
const Plants = lazy(() => import('./pages/Plants'))
const About = lazy(() => import('./pages/About'))
const Settings = lazy(() => import('./pages/Settings'))

function PlantRoutes() {
  return (
    <PlantProvider>
      <Suspense fallback={<Loading />}>
        <Outlet />
      </Suspense>
    </PlantProvider>
  )
}

const router = createBrowserRouter([
  {
    element: <Layout />,
    errorElement: <ErrorPage />,
    children: [
      { index: true, element: <Navigate to="/p/demo/overview" replace /> },
      {
        path: 'p/:plantId',
        element: <PlantRoutes />,
        errorElement: <ErrorPage />,
        children: [
          { index: true, element: <Navigate to="overview" replace /> },
          { path: 'overview', element: <Overview /> },
          { path: 'twin', element: <Twin /> },
          { path: 'savings', element: <Savings /> },
          { path: 'whatif', element: <WhatIf /> },
          { path: 'assistant', element: <Assistant /> },
          { path: 'documents', element: <Documents /> },
          { path: 'accuracy', element: <Accuracy /> },
          { path: 'settings', element: <Settings /> },
        ],
      },
      { path: 'designer/:plantId', element: <Suspense fallback={<Loading />}><Designer /></Suspense> },
      { path: 'plants', element: <Suspense fallback={<Loading />}><Plants /></Suspense> },
      { path: 'about', element: <Suspense fallback={<Loading />}><About /></Suspense> },
      { path: '*', element: <Navigate to="/p/demo/overview" replace /> },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
