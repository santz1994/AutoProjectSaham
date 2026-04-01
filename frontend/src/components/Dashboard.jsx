import React from 'react'
import Portfolio from './Portfolio'
import Events from './Events'
import Training from './Training'
import OrderBook from './execution/OrderBook'
import OrderEntryForm from './execution/OrderEntryForm'

export default function Dashboard() {
  return (
    <div className="dashboard">
      <div className="left">
          <Portfolio />
          <OrderEntryForm />
          <OrderBook />
          <Training />
      </div>
      <div className="right">
        <Events />
      </div>
    </div>
  )
}
